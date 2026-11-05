"""Local, dependency-free fact extraction from an assistant's answer.

Used by the web bridge's ``[+ Save Facts]`` button. Nothing leaves the device:
the default extractor is regex/heuristics; setting ``MEMTY_OLLAMA_MODEL`` uses a
local Ollama model instead, falling back to heuristics if it is unavailable.
Extraction only *proposes* facts; the user reviews them before anything is saved.

Facts are kept atomic and readable by a chat assistant: headings and pasted
Memty capsules are ignored, bare file paths collapse into one ``files`` fact,
and each code block becomes a one-line summary of what it defines, never code.
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
MAX_CODE_FACTS = 2

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
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_CITATION = re.compile(r"\[\d+(?:,\s*\d+)*\]")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")
_SLOT_CHARS = re.compile(r"[^a-z0-9]+")

# Capsules a user pasted into the chat must never be re-extracted as new facts.
_CAPSULE = re.compile(r"<memty_state\b.*?(?:</memty_state>|\Z)|\[Memty context.*?(?:\[/Memty\]|\Z)", re.S)
_FENCE = re.compile(r"```([\w+#.-]*)[^\n]*\n(.*?)(?:```|\Z)", re.S)
_CODE_EXT = (r"(?:py|js|mjs|cjs|ts|tsx|jsx|json|md|html|css|scss|sql|toml|ya?ml|sh|ps1|txt|cfg|ini"
             r"|go|rs|java|kt|rb|php|c|h|cpp|cs|swift)")
_PATH = re.compile(r"^(?:[\w.~@-]+[/\\])+[\w.@-]+/?$|^[\w.-]+\.%s$" % _CODE_EXT, re.I)
_FILE_KEY = re.compile(r"\b(?:file|files|path|script|module)\b", re.I)
_DEFINES = [
    re.compile(r"^\s*(?:async\s+)?def\s+(\w+)", re.M),
    re.compile(r"^\s*(?:export\s+)?(?:default\s+)?class\s+(\w+)", re.M),
    re.compile(r"\bfunction\s+(\w+)\s*\("),
    re.compile(r"\b(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>"),
    re.compile(r"\bCREATE\s+(?:VIRTUAL\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`]?(\w+)", re.I),
]
_FILE_HINT = re.compile(r"^\s*(?:#|//|/\*|<!--|--)\s*((?:[\w.-]+/)*[\w.-]+\.%s)\b" % _CODE_EXT, re.I)
_LANGS = {"py": "Python", "python": "Python", "js": "JavaScript", "javascript": "JavaScript",
          "ts": "TypeScript", "typescript": "TypeScript", "tsx": "TypeScript", "jsx": "JavaScript",
          "sql": "SQL", "sh": "Shell", "bash": "Shell", "json": "JSON", "html": "HTML", "css": "CSS"}


def _looks_like_code(raw: str, key: str | None, value: str) -> bool:
    if _CODE.search(raw) or _TYPE_HINT.match(value):
        return True
    # "snake_case_key: value" with a dotted call or path in the value.
    return bool(key and "_" in key and " " not in key and re.search(r"\w\.\w+\(", value))


def _clean(text: str) -> str:
    text = _LINK.sub(r"\1", text)
    text = _CITATION.sub("", text)
    text = re.sub(r"[*`#>]+|(?<!\w)_+|_+(?!\w)", "", text)  # keep snake_case names intact
    return re.sub(r"\s+", " ", text).strip(" -:;,")


_STOPWORDS = frozenset("""a an the this that these those it its is are was were be been being am
of to in on at by for with from as into onto over under about and or but nor so yet if then than
i you he she we they me my your our their his her them us do does did done have has had will would
can could should may might must shall not no only also just very more most some any all each every
which who whom whose what when where why how there here""".split())


def _title_for(value: str) -> str:
    """A short readable title for a fact that had no ``Key:``: its first content words."""
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9+#-]*", value) if w.casefold() not in _STOPWORDS]
    return "_".join(words[:3]).casefold()


def _slot_for(key: str | None, value: str) -> str:
    for candidate in (key, _title_for(value)):
        if candidate:
            slot = _SLOT_CHARS.sub("_", candidate.casefold()).strip("_")[:48].strip("_")
            if slot and slot[0].isalnum():
                return slot
    return "note_" + hashlib.sha1(value.casefold().encode("utf-8")).hexdigest()[:8]


def _is_heading(value: str) -> bool:
    """Title-cased, unpunctuated lines are section headings, not facts."""
    if value[-1:] in ".!:;" or len(value.split()) > 12:
        return False
    words = [w.strip("()[],\"'") for w in value.split()]
    words = [w for w in words if w and w[0].isalpha()]
    return len(words) >= 2 and sum(w[0].isupper() for w in words) / len(words) >= 0.7


def _is_path(key: str | None, value: str) -> bool:
    if " " in value or not _PATH.match(value):
        return False
    return "/" in value or "\\" in value or not key or bool(_FILE_KEY.search(key))


def _fact(line: str) -> dict | None:
    raw = line.strip()
    line = _clean(line)
    if len(line) < 3 or line.endswith("?"):
        return None
    key, value = None, line
    match = _KEY_VALUE.match(line)
    if match and len(match.group(1).split()) <= 5:
        key, value = match.group(1).strip(), match.group(2).strip()
    if _is_path(key, value):
        return {"slot": "files", "value": value, "path": True}
    if _looks_like_code(raw, key, value):
        return None
    if not key and (len(value.split()) < 3 or _is_heading(value)):
        return None  # fragments and headings are not atomic facts
    value = truncate_tokens(value, FACT_TOKEN_LIMIT)
    if not value:
        return None
    return {"slot": _slot_for(key, value), "value": value}


def summarize_code(code: str, lang: str = "") -> dict | None:
    """One readable fact about a code block: its language, file, and what it defines."""
    names: list[str] = []
    for pattern in _DEFINES:
        for match in pattern.finditer(code):
            name = match.group(1)
            if not name.startswith("__") and name not in names:
                names.append(name)
    if not names:
        return None
    lang = _LANGS.get(lang.casefold(), lang) if lang else ""
    if not lang:
        lang = ("Python" if re.search(r"^\s*(?:async\s+)?(?:def|class)\s", code, re.M) else
                "SQL" if re.search(r"\bCREATE\s+TABLE\b", code, re.I) else "JavaScript")
    file_hint = _FILE_HINT.search(code)
    where = f" in {file_hint.group(1)}" if file_hint else ""
    shown = ", ".join(names[:8]) + (f" and {len(names) - 8} more" if len(names) > 8 else "")
    value = truncate_tokens(f"{lang} code{where} defines {shown}", FACT_TOKEN_LIMIT)
    return {"slot": _slot_for(f"{lang} code", value), "value": value}


def _mostly_code(lines: list[str]) -> bool:
    lines = [line for line in lines if line.strip()]
    return len(lines) >= 3 and sum(bool(_CODE.search(line)) for line in lines) / len(lines) >= 0.6


def _add(facts: list[dict], seen_slots: set[str], slot: str, value: str) -> None:
    unique, counter = slot, 2
    while unique in seen_slots:  # two bullets with the same key: keep both
        unique, counter = f"{slot[:45]}_{counter}", counter + 1
    seen_slots.add(unique)
    facts.append({"slot": unique, "value": value})


def extract_heuristic(text: str, max_facts: int = MAX_FACTS) -> list[dict]:
    """Bullets and ``Key: value`` lines first; otherwise short declarative sentences.

    Code blocks are summarized (never copied); bare file paths become one fact.
    """
    text = _CAPSULE.sub("\n", str(text)[:MAX_INPUT_CHARS])
    code_facts = [fact for lang, body in _FENCE.findall(text)
                  if (fact := summarize_code(body, lang))][:MAX_CODE_FACTS]
    text = _FENCE.sub("\n", text)
    lines = text.splitlines()
    if _mostly_code(lines):  # the user selected a raw code sample
        fact = summarize_code(text)
        return [fact] if fact else []
    candidates = [m.group(1) for m in map(_BULLET.match, lines) if m]
    candidates += [line for line in lines if not _BULLET.match(line) and _KEY_VALUE.match(_clean(line))]
    if not candidates:
        prose = " ".join(line.strip() for line in lines if line.strip())
        candidates = [s for s in _SENTENCE.split(prose) if 4 <= len(s.split()) <= 30][:5]
    facts: list[dict] = []
    seen_slots: set[str] = set()
    seen_values: set[str] = set()
    paths: list[str] = []
    room = max_facts - len(code_facts)
    for candidate in candidates:
        fact = _fact(candidate)
        if fact and fact.get("path"):
            if fact["value"] not in paths:
                paths.append(fact["value"])
            continue
        if not fact or fact["value"].casefold() in seen_values or len(facts) >= room:
            continue
        seen_values.add(fact["value"].casefold())
        _add(facts, seen_slots, fact["slot"], fact["value"])
    extras = list(code_facts)
    if paths:
        extras.insert(0, {"slot": "files", "value": truncate_tokens(", ".join(paths), FACT_TOKEN_LIMIT)})
    for fact in extras:
        _add(facts, seen_slots, fact["slot"], fact["value"])
    return facts[:max_facts]


def extract_ollama(text: str, model: str, *, host: str = "http://127.0.0.1:11434",
                   timeout: float = 15.0, max_facts: int = MAX_FACTS) -> list[dict]:
    """Ask a local Ollama model for facts; the result is validated like heuristics."""
    prompt = ("Extract up to %d durable, atomic facts from the text as JSON: "
              '{"facts": [{"slot": "short_snake_case_key", "value": "one self-contained fact under 25 words"}]}. '
              "Each fact states one thing (a decision, preference, tool, name, number, or date) and "
              "makes sense on its own. Never copy code: summarize a code block as one fact saying what "
              "it defines or does. Skip headings, questions, and filler. Only facts stated in the text."
              "\n\nTEXT:\n%s" % (max_facts, _CAPSULE.sub("", str(text)[:MAX_INPUT_CHARS])))
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
