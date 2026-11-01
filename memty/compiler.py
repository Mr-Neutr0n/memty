"""Deterministic <600-token context compiler with a hard privacy gate."""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Any
from xml.sax.saxutils import escape

from .ledger import (LOCAL_PROVIDERS, _PROVIDER, _normalize_namespace, _terms)
from .tokens import estimate_tokens, truncate_tokens
from .vectors import cosine, unpack_vector

if TYPE_CHECKING:  # pragma: no cover - import cycle only for type checkers
    from .ledger import MemtyLedger


class LocalRoutingRequired(RuntimeError):
    """A matched SECRET fact may not leave the device.

    The caller (router/SDK) should switch to the suggested local provider and
    compile the context again.  No secret value is included on the exception.
    """

    def __init__(self, provider: str, *, namespace: str | None = None,
                 slot: str | None = None, suggested_provider: str = "ollama"):
        self.provider = provider
        self.namespace = namespace
        self.slot = slot
        self.suggested_provider = suggested_provider
        target = f"{namespace}.{slot}" if namespace and slot else "a secret slot"
        super().__init__(
            f"SECRET memory matched {target}; provider '{provider}' is not local. "
            f"Route this request to '{suggested_provider}'."
        )

    def as_dict(self) -> dict[str, Any]:
        return {"error": "local_routing_required", "provider": self.provider,
                "suggested_provider": self.suggested_provider,
                "namespace": self.namespace, "slot": self.slot}


class ContextCompiler:
    """Compile allowed atomic state, one summary, and semantic snippets."""

    # Section ceilings at the default 600-token budget.  They scale down for a
    # smaller budget and never grow beyond the published maxima for a larger one.
    SLOT_CEILING = 250
    SUMMARY_CEILING = 200
    SEMANTIC_CEILING = 150
    DEFAULT_BUDGET = 600

    def __init__(self, ledger: "MemtyLedger"):
        self.ledger = ledger

    # ------------------------------------------------------------------
    def compile(self, query: str, *, provider: str, token_budget: int = DEFAULT_BUDGET,
                namespace: str | None = None,
                semantic_scores: dict[str, float] | None = None,
                query_embedding: list[float] | None = None) -> dict[str, Any]:
        provider = str(provider or "").strip()
        if not _PROVIDER.fullmatch(provider):
            raise ValueError("provider is required and must be a provider identifier")
        if not isinstance(token_budget, int) or not 1 <= token_budget <= 20_000:
            raise ValueError("token_budget must be an integer between 1 and 20000")
        query = "" if query is None else str(query).strip()
        namespace = _normalize_namespace(namespace) if namespace else None

        provider_key = provider.casefold()
        local = provider_key in LOCAL_PROVIDERS
        trusted = local or provider_key in self.ledger.trusted_providers
        query_terms = _terms(query)
        scores = {str(key): float(value) for key, value in (semantic_scores or {}).items()}

        with self.ledger._connect() as db:
            rows = self.ledger.candidate_facts(db, query_terms, namespace, set(scores), query_embedding)
            ranked: list[tuple[float, dict[str, Any], sqlite3.Row]] = []
            for row in rows:
                fact = self.ledger._fact(row, include_embedding=False)
                if fact["tombstone"] or not self._provider_allowed(fact, provider_key, trusted):
                    continue
                overlap = (len(query_terms & _terms(
                    f"{fact['namespace']} {fact['slot']} {fact['value']}")) / len(query_terms)
                    if query_terms else 0.0)
                semantic = max(0.0, min(1.0, scores.get(fact["id"], 0.0)))
                if query_embedding and row["embedding"]:
                    semantic = max(semantic, max(0.0, min(
                        1.0, cosine(query_embedding, unpack_vector(row["embedding"])))))
                if query_terms and overlap == 0.0 and semantic < 0.15 and not (
                        namespace and fact["namespace"] == namespace):
                    continue
                if not query_terms and not namespace and not query_embedding:
                    continue
                score = 0.55 * semantic + 0.45 * overlap
                if namespace and fact["namespace"] == namespace:
                    score += 0.15
                if fact["verification_state"] in {"USER_CONFIRMED", "SPEC_LOCKED"}:
                    score += 0.05
                score += 0.05 * float(fact["confidence"])
                fact["_semantic_score"] = semantic
                ranked.append((score, fact, row))
            ranked.sort(key=lambda item: (-item[0], item[1]["namespace"], item[1]["slot"], item[1]["id"]))

            # Hard privacy gate: a SECRET fact that matches this query forces
            # local routing regardless of the provider's allow-list.
            if not local:
                for _, fact, _row in ranked:
                    if fact["sensitivity"] == "SECRET":
                        raise LocalRoutingRequired(provider, namespace=fact["namespace"],
                                                   slot=fact["slot"])

            summary = self._select_summary(db, query_terms, namespace, query_embedding,
                                           provider_key, trusted)
            sensitive_summary = False
            if summary is not None and not trusted:
                sensitive_summary = self.ledger.namespace_has_sensitive(db, summary["namespace"])
            if sensitive_summary:
                summary = None

        return self._pack(ranked, summary, provider=provider, provider_key=provider_key,
                          local=local, trusted=trusted, token_budget=token_budget,
                          namespace=namespace, eligible_count=len(ranked))

    # ------------------------------------------------------------------
    @staticmethod
    def _provider_allowed(fact: dict[str, Any], provider_key: str, trusted: bool) -> bool:
        blocked = {item.casefold() for item in fact["blocked_providers"]}
        if provider_key in blocked:
            return False
        allowed = {item.casefold() for item in fact["allowed_providers"]}
        if allowed and provider_key not in allowed:
            return False
        if fact["sensitivity"] == "INTERNAL" and not trusted and provider_key not in allowed:
            return False
        return True

    def _select_summary(self, db: sqlite3.Connection, query_terms: set[str],
                        namespace: str | None, query_embedding: list[float] | None,
                        provider_key: str, trusted: bool) -> dict[str, Any] | None:
        candidates = self.ledger.candidate_summaries(db, query_terms, namespace, query_embedding)
        best: tuple[float, sqlite3.Row] | None = None
        for row in candidates:
            overlap = (len(query_terms & _terms(f"{row['namespace']} {row['summary_text']}"))
                       / len(query_terms) if query_terms else 0.0)
            semantic = (max(0.0, min(1.0, cosine(query_embedding, unpack_vector(row["embedding"]))))
                        if query_embedding and row["embedding"] else 0.0)
            score = 0.55 * semantic + 0.45 * overlap
            if namespace and row["namespace"] == namespace:
                score += 0.5
            elif not query_terms:
                continue
            if score > 0 and (best is None or score > best[0]):
                best = (score, row)
        if best is None:
            return None
        row = best[1]
        return {"namespace": row["namespace"], "summary_text": row["summary_text"],
                "token_count": row["token_count"], "updated_at": row["updated_at"]}

    # ------------------------------------------------------------------
    def _pack(self, ranked: list[tuple[float, dict[str, Any], sqlite3.Row]], summary: dict[str, Any] | None,
              *, provider: str, provider_key: str, local: bool, trusted: bool,
              token_budget: int, namespace: str | None, eligible_count: int) -> dict[str, Any]:
        header = f'<memty_state v="1" provider="{provider}">'
        if estimate_tokens(header + "</memty_state>") > token_budget:
            return self._empty(provider, token_budget, eligible_count)

        overhead = estimate_tokens(header + "</memty_state><slots></slots><summary></summary><semantic></semantic>")
        usable = max(0, token_budget - overhead)
        slot_cap = min(self.SLOT_CEILING, int(usable * 0.42))
        summary_cap = min(self.SUMMARY_CEILING, int(usable * 0.33))
        semantic_cap = min(self.SEMANTIC_CEILING, max(0, usable - slot_cap - summary_cap))

        slots: list[str] = []
        semantic_lines: list[str] = []
        citations: list[dict[str, Any]] = []
        redactions: dict[str, str] = {}
        placeholder_by_id: dict[str, str] = {}
        used: set[str] = set()
        counter = 0

        def needs_redaction(fact: dict[str, Any]) -> bool:
            allowed = {item.casefold() for item in fact["allowed_providers"]}
            fact_trusted = local or trusted or provider_key in allowed
            return bool(fact["ephemeral_redaction"]) or (
                fact["sensitivity"] == "CONFIDENTIAL" and not fact_trusted)

        def placeholder_for(fact: dict[str, Any]) -> str:
            nonlocal counter
            placeholder = placeholder_by_id.get(fact["id"])
            if placeholder is None:
                counter += 1
                placeholder = f"<MEMTY_REDACTED_SLOT_{counter}>"
                placeholder_by_id[fact["id"]] = placeholder
                redactions[placeholder] = fact["value"]
            return placeholder

        def line_for(fact: dict[str, Any], value: str) -> str:
            return f"{fact['namespace']}.{fact['slot']}={json.dumps(value, ensure_ascii=False)}"

        def probe_line(fact: dict[str, Any]) -> str:
            # Use a placeholder-shaped value while checking the budget so we do
            # not create a redaction mapping for a fact that never gets injected.
            value = "<MEMTY_REDACTED_SLOT_99>" if needs_redaction(fact) else fact["value"]
            return line_for(fact, value)

        def citation(fact: dict[str, Any], section: str) -> dict[str, Any]:
            return {"id": fact["id"], "namespace": fact["namespace"], "slot": fact["slot"],
                    "value": placeholder_by_id.get(fact["id"], fact["value"]),
                    "verification_state": fact["verification_state"],
                    "sensitivity": fact["sensitivity"], "section": section}

        def render(slot_lines: list[str], summary_line: str | None,
                   semantic_snippets: list[str]) -> str:
            parts = [header]
            if slot_lines:
                parts.extend(["<slots>", *slot_lines, "</slots>"])
            if summary_line:
                parts.append(summary_line)
            if semantic_snippets:
                parts.extend(["<semantic>", *semantic_snippets, "</semantic>"])
            parts.append("</memty_state>")
            return "\n".join(parts)

        # Cheap additive accounting avoids re-tokenizing the whole block for
        # every candidate.  The final render plus safety loop is exact.
        base_tokens = estimate_tokens(header + "</memty_state>") + 4
        slots_tag_tokens = estimate_tokens("<slots></slots>")
        semantic_tag_tokens = estimate_tokens("<semantic></semantic>")

        def fits(extra_slot: int = 0, extra_semantic: int = 0) -> bool:
            total = base_tokens + extra_slot + extra_semantic
            if slots or extra_slot:
                total += slots_tag_tokens
            if summary_line:
                total += estimate_tokens(summary_line)
            if semantic_lines or extra_semantic:
                total += semantic_tag_tokens
            return total <= token_budget

        summary_line: str | None = None
        if summary is not None:
            summary_namespace = summary["namespace"]
            text = truncate_tokens(summary["summary_text"], max(1, summary_cap - 12))
            candidate = f'<summary ns="{escape(summary_namespace)}">{escape(text)}</summary>'
            if base_tokens + estimate_tokens(candidate) <= token_budget:
                summary_line = candidate

        slot_used = 0
        for _score, fact, _row in ranked:
            if len(slots) >= 32:
                break
            if fact["id"] in used:
                continue
            probe = probe_line(fact)
            cost = estimate_tokens(probe)
            if slot_used + cost > slot_cap:
                continue
            if not fits(extra_slot=cost + 1):
                continue
            value = placeholder_for(fact) if needs_redaction(fact) else fact["value"]
            slots.append(line_for(fact, value))
            used.add(fact["id"])
            slot_used += cost
            citations.append(citation(fact, "slots"))

        semantic_used = 0
        semantic_candidates = sorted(
            ranked,
            key=lambda item: (-float(item[1].get("_semantic_score", 0.0)), -item[0],
                              item[1]["namespace"], item[1]["slot"], item[1]["id"]))
        for _score, fact, _row in semantic_candidates:
            if len(semantic_lines) >= 3:
                break
            if fact["id"] in used:
                continue
            probe = probe_line(fact)
            cost = estimate_tokens(probe)
            if semantic_used + cost > semantic_cap:
                continue
            if not fits(extra_semantic=cost + 1):
                continue
            value = placeholder_for(fact) if needs_redaction(fact) else fact["value"]
            semantic_lines.append(line_for(fact, value))
            used.add(fact["id"])
            semantic_used += cost
            citations.append(citation(fact, "semantic"))

        text = render(slots, summary_line, semantic_lines)
        # Final hard guarantee, even if a caller changed the ceilings above.
        def drop_last_citation(section: str) -> None:
            for index in range(len(citations) - 1, -1, -1):
                if citations[index].get("section") == section:
                    citations.pop(index)
                    return

        while estimate_tokens(text) > token_budget and (semantic_lines or summary_line or slots):
            if semantic_lines:
                semantic_lines.pop()
                drop_last_citation("semantic")
            elif summary_line:
                summary_line = None
            else:
                slots.pop()
                drop_last_citation("slots")
            text = render(slots, summary_line, semantic_lines)

        if not slots and summary_line is None and not semantic_lines:
            return self._empty(provider, token_budget, eligible_count)

        if summary_line is not None:
            citations.insert(0, {"type": "summary", "namespace": summary["namespace"],
                                 "value": summary["summary_text"], "token_count": summary["token_count"],
                                 "section": "summary"})

        redactions = {key: value for key, value in redactions.items() if key in text}
        return {"text": text, "citations": citations, "redactions": redactions,
                "provider": provider, "approx_tokens": estimate_tokens(text),
                "token_budget": token_budget, "eligible_count": eligible_count,
                "injected_count": sum(1 for item in citations if item.get("type") != "summary"),
                "sections": {"slots": len(slots), "summary": int(summary_line is not None),
                             "semantic": len(semantic_lines)},
                "requires_local": False}

    @staticmethod
    def _empty(provider: str, token_budget: int, eligible_count: int) -> dict[str, Any]:
        return {"text": "", "citations": [], "redactions": {}, "provider": provider,
                "approx_tokens": 0, "token_budget": token_budget,
                "eligible_count": eligible_count, "injected_count": 0,
                "sections": {"slots": 0, "summary": 0, "semantic": 0},
                "requires_local": False}
