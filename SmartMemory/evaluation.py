"""Small deterministic evaluation harness for memory-state regressions."""

from __future__ import annotations

from typing import Any

from .ledger import MemoryLedger


def evaluate_cases(ledger: MemoryLedger, cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Measure stale-value bleed, tombstone stickiness, and context density.

    Each case has ``query``, ``provider`` and optional ``token_budget`` and
    ``stale_values``. Set ``deleted_slot`` and ``deleted_value`` to probe the
    explicit user-delete guard for a previously removed slot.
    """
    stale_denominator = stale_hits = sticky_denominator = sticky_passes = 0
    fact_count = token_count = 0
    details = []
    for index, case in enumerate(cases):
        compiled = ledger.context(str(case.get("query", "")),
                                  provider=str(case.get("provider", "local")),
                                  token_budget=int(case.get("token_budget", 900)),
                                  as_of=case.get("as_of"))
        text = compiled["text"].casefold()
        stale = [str(value) for value in case.get("stale_values", []) if str(value)]
        stale_denominator += bool(stale)
        leaked = [value for value in stale if value.casefold() in text]
        stale_hits += bool(leaked)
        fact_count += len(compiled["citations"])
        token_count += compiled["approx_tokens"]

        sticky_result = None
        if case.get("deleted_slot") and case.get("deleted_value"):
            sticky_denominator += 1
            state = ledger.slot_state(str(case["namespace"]), str(case["slot_key"]))
            sticky_result = bool(state and state["status"] == "DELETED"
                                 and str(case["deleted_value"]).casefold() not in text)
            sticky_passes += sticky_result
        details.append({"case": index, "stale_values_found": leaked,
                        "context_facts": len(compiled["citations"]),
                        "approx_tokens": compiled["approx_tokens"],
                        "deleted_slot_blocked": sticky_result})

    return {
        "case_count": len(cases),
        "stale_fact_bleed_rate": stale_hits / stale_denominator if stale_denominator else None,
        "stale_fact_cases": stale_denominator,
        "correction_stickiness_score": sticky_passes / sticky_denominator if sticky_denominator else None,
        "deleted_slot_cases": sticky_denominator,
        "token_density_facts_per_100_tokens": 100 * fact_count / token_count if token_count else 0.0,
        "total_injected_facts": fact_count,
        "approx_tokens": token_count,
        "details": details,
        "note": "Approximate token counts use 4 characters per token; compare only under the same tokenizer convention.",
    }
