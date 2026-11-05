"""Local, dependency-free fact extraction from an assistant's answer.

Used by the web bridge's ``[+ Save Facts]`` button. Nothing leaves the device:
the default extractor is regex/heuristics; setting ``MEMTY_OLLAMA_MODEL`` uses a
local Ollama model instead, falling back to heuristics if it is unavailable.
Extraction only *proposes* facts; the user reviews them before anything is saved.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from urllib import request as urlrequest

from .ledger import FACT_TOKEN_LIMIT
from .tokens import estimate_tokens, truncate_tokens

MAX_FACTS = 12
MAX_INPUT_CHARS = 50_000

_BULLET = re.compile(r"^\s*(?:[-*•●▪]|\d{1,2}[.)])\s+(.*\S)\s*$")
# No "=" separator: "conn = sqlite3.connect(...)" is code, not a fact.
_KEY_VALUE = re.compile(r"^([A-Za-z][\w .'/()-]{0,48}?)\s*[:—]\s+(.{2,})$")
# Lines from code samples: calls, assignments, keywords, statement punctuation.
_CODE = re.compile(
    r"\bself\.|^\s*(?:def|class|import|from|return|const|let|var|function|if|for|while)\b"
    r"|=>|==|!=|;\s*$|[{}]|^\s*[\])]|\w\([^)]*\)\s*[:;,]?\s*$|^\s*[\w.\[\]]+\s*[+\-*/]?=\s*\S"
    r"|^\s*(?:#|//)")
# Type annotations such as "namespace: str" or "items: list[str] | None".
_TYPE_HINT = re.compile(
    r"^(?:str|int|float|bool|bytes|dict|list|tuple|set|object|None|Any|Path|"
    r"(?:Optional|Union|List|Dict|Tuple|Set|list|dict|tuple|set)\[.*\])(?:\s*\|\s*None)?"
    r"(?:\s*=\s*.+)?$")


def _looks_like_code(raw: str, key: str | None, value: str) -> bool:
    if _CODE.search(raw) or _TYPE_HINT.match(value):
        return True
    # "snake_case_key: value" with a dotted call or path in the value.
    return bool(key and "_" in key and " " not in key and re.search(r"\w\.\w+\(", value))
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_CITATION = re.compile(r"\[\d+(?:,\s*\d+)*\]")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")
_SLOT_CHARS = re.compile(r"[^a-z0-9]+")


def _clean(text: str) -> str:
    text = _LINK.sub(r"\1", text)
    text = _CITATION.sub("", text)
    text = re.sub(r"[*_`#>]+", "", text)
    return re.sub(r"\s+", " ", text).strip(" -:;,")


def _slot_for(key: str | None, value: str) -> str:
    if key:
        slot = _SLOT_CHARS.sub("_", key.casefold()).strip("_")[:48].strip("_")
        if slot and slot[0].isalnum():
            return slot
    return "note_" + hashlib.sha1(value.casefold().encode("utf-8")).hexdigest()[:8]


def _fact(line: str) -> dict | None:
    raw = line.strip()
    line = _clean(line)
    if len(line) < 3 or line.endswith("?"):
        return None
    key, value = None, line
    match = _KEY_VALUE.match(line)
    if match and len(match.group(1).split()) <= 5:
        key, value = match.group(1).strip(), match.group(2).strip()
    if _looks_like_code(raw, key, value):
        return None
    value = truncate_tokens(value, FACT_TOKEN_LIMIT)
    if not value:
        return None
    return {"slot": _slot_for(key, value), "value": value}


def extract_heuristic(text: str, max_facts: int = MAX_FACTS) -> list[dict]:
    """Bullets and ``Key: value`` lines first; otherwise short declarative sentences."""
    text = re.sub(r"```.*?(?:```|\Z)", "\n", str(text)[:MAX_INPUT_CHARS], flags=re.S)
    lines = text.splitlines()
    candidates = [m.group(1) for m in map(_BULLET.match, lines) if m]
    candidates += [line for line in lines if not _BULLET.match(line) and _KEY_VALUE.match(_clean(line))]
    if not candidates:
        prose = " ".join(line.strip() for line in lines if line.strip())
        candidates = [s for s in _SENTENCE.split(prose) if 4 <= len(s.split()) <= 30][:5]
    facts, seen_slots, seen_values = [], set(), set()
    for candidate in candidates:
        fact = _fact(candidate)
        if not fact or fact["value"].casefold() in seen_values:
            continue
        slot, counter = fact["slot"], 2
        while slot in seen_slots:  # two bullets with the same key: keep both
            slot, counter = f"{fact['slot'][:45]}_{counter}", counter + 1
        seen_slots.add(slot)
        seen_values.add(fact["value"].casefold())
        facts.append({"slot": slot, "value": fact["value"]})
        if len(facts) >= max_facts:
            break
    return facts


def extract_ollama(text: str, model: str, *, host: str = "http://127.0.0.1:11434",
                   timeout: float = 30.0, max_facts: int = MAX_FACTS) -> list[dict]:
    """Ask a local Ollama model for facts; the result is validated like heuristics."""
    prompt = ("Extract up to %d durable facts from the text as JSON: "
              '{"facts": [{"slot": "short_snake_case_key", "value": "fact under 30 words"}]}. '
              "Only facts stated in the text.\n\nTEXT:\n%s" % (max_facts, str(text)[:MAX_INPUT_CHARS]))
    body = json.dumps({"model": model, "prompt": prompt, "format": "json", "stream": False}).encode()
    req = urlrequest.Request(host.rstrip("/") + "/api/generate", data=body,
                             headers={"Content-Type": "application/json"})
    with urlrequest.urlopen(req, timeout=timeout) as response:
        payload = json.loads(json.loads(response.read())["response"])
    facts, seen = [], set()
    for item in payload.get("facts", []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict) or not str(item.get("value", "")).strip():
            continue
        value = truncate_tokens(_clean(str(item["value"])), FACT_TOKEN_LIMIT)
        slot = _slot_for(str(item.get("slot", "")), value)
        if value and slot not in seen and estimate_tokens(value) <= FACT_TOKEN_LIMIT:
            seen.add(slot)
            facts.append({"slot": slot, "value": value})
    return facts[:max_facts]


def extract_facts(text: str, *, max_facts: int = MAX_FACTS) -> dict:
    """Return ``{"facts": [...], "method": "ollama" | "heuristic"}``."""
    model = os.getenv("MEMTY_OLLAMA_MODEL", "").strip()
    if model:
        try:
            facts = extract_ollama(text, model, max_facts=max_facts,
                                   host=os.getenv("MEMTY_OLLAMA_HOST", "http://127.0.0.1:11434"))
            if facts:
                return {"facts": facts, "method": "ollama"}
        except (OSError, ValueError, KeyError, TypeError):
            pass  # Ollama not running or returned junk: fall back to heuristics.
    return {"facts": extract_heuristic(text, max_facts), "method": "heuristic"}
