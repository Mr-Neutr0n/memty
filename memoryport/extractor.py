"""Model-agnostic durable-fact extraction into canonical ledger slots."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from .ledger import MemoryLedger


_SECRET_LIKE = re.compile(
    r"(?i)(?:\b(?:api[_ -]?key|password|secret|access[_ -]?token|private[_ -]?key)\b\s*(?:[:=]|is\s+)\s*\S+|"
    r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})\b)"
)

_INSTRUCTIONS = """Extract at most five durable facts that the user explicitly states in their message.
Return only JSON in this schema:
{"memories":[{"namespace":"work.project","slot_key":"primary_database","value":"MongoDB Atlas","confidence":0.9,"source_quote":"exact substring from the user message","sensitivity_tier":"PERSONAL","allowed_providers":[],"blocked_providers":[],"ephemeral_redaction":false,"valid_from":null}]}
Use stable canonical namespace and slot keys. Return the same slot for a correction to an earlier value. Ignore questions, guesses, one-off tasks, secrets, credentials, and sensitive personal data. Do not derive facts from the assistant response. Keep values concise and factual. If nothing qualifies, return {"memories":[]}.
"""


class MemoryExtractor:
    """Run a caller-supplied model function and validate its proposed memories.

    ``generate_json`` receives a prompt and returns a JSON string or parsed
    object. The vault itself never contacts a model provider.
    """

    def __init__(self, ledger: MemoryLedger, generate_json: Callable[[str], Any], *,
                 minimum_confidence: float = 0.8, max_facts: int = 5):
        if not 0 <= minimum_confidence <= 1:
            raise ValueError("minimum_confidence must be between 0 and 1")
        if not 1 <= max_facts <= 20:
            raise ValueError("max_facts must be between 1 and 20")
        self.ledger = ledger
        self.generate_json = generate_json
        self.minimum_confidence = minimum_confidence
        self.max_facts = max_facts

    def ingest_turn(self, user_message: str, assistant_response: str = "", *,
                    conversation_id: str | None = None, model_id: str | None = None) -> dict[str, Any]:
        user_message = str(user_message).strip()
        if not user_message:
            return {"saved": [], "skipped": 0}
        prompt = (_INSTRUCTIONS + "\nUSER MESSAGE:\n" + user_message[:12000]
                  + "\nASSISTANT RESPONSE (context only; do not extract facts from it):\n"
                  + str(assistant_response)[:4000])
        raw = self.generate_json(prompt)
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(parsed, dict) or not isinstance(parsed.get("memories", []), list):
            raise ValueError("extractor must return a JSON object with a memories list")

        saved = []
        skipped = 0
        user_folded = user_message.casefold()
        for candidate in parsed.get("memories", [])[:self.max_facts]:
            if not isinstance(candidate, dict):
                skipped += 1
                continue
            quote = candidate.get("source_quote")
            value = candidate.get("value")
            try:
                confidence = float(candidate.get("confidence", 0))
            except (TypeError, ValueError):
                skipped += 1
                continue
            if (not isinstance(quote, str) or not quote.strip() or quote.casefold() not in user_folded
                or not isinstance(value, str) or not value.strip() or confidence < self.minimum_confidence
                or _SECRET_LIKE.search(value) or _SECRET_LIKE.search(quote)):
                skipped += 1
                continue
            tier = str(candidate.get("sensitivity_tier", "PERSONAL")).upper()
            if tier in {"SECRET", "CONFIDENTIAL"}:
                skipped += 1
                continue
            try:
                record = self.ledger.record(
                    str(candidate.get("namespace", "personal.general")), str(candidate.get("slot_key", "fact")),
                    value, confidence=min(1.0, confidence), verification_state="AUTO_EXTRACTED",
                    sensitivity_tier=tier,
                    allowed_providers=candidate.get("allowed_providers") or [],
                    blocked_providers=candidate.get("blocked_providers") or [],
                    ephemeral_redaction=bool(candidate.get("ephemeral_redaction", False)),
                    valid_from=candidate.get("valid_from"), source_conversation_id=conversation_id,
                    source_message=quote.strip(), extracted_by_model=model_id,
                )
            except ValueError:
                skipped += 1
                continue
            saved.append(record)
        return {"saved": saved, "skipped": skipped}

