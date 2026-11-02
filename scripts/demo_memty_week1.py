"""Human-readable, temporary-database walkthrough of Memty Week 1 behavior."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memty import LocalRoutingRequired, MemtyLedger, TombstonedSlot, estimate_tokens


def passed(message: str) -> None:
    print(f"[PASS] {message}")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    passed(message)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="memty-week1-demo-") as directory:
        path = Path(directory) / "ledger.sqlite3"
        with MemtyLedger(path) as vault:
            first = vault.record(
                "demo.preferences", "editor", "VS Code",
                verification_state="USER_CONFIRMED",
            )
            updated = vault.record(
                "demo.preferences", "editor", "Neovim",
                verification_state="USER_CONFIRMED",
            )
            history = vault.history("demo.preferences", "editor")
            require(updated["version"] == 2 and len(history) == 2,
                    "one active value per slot; replacement keeps version history")

            vault.record(
                "demo.project", "database", "Postgres 16",
                verification_state="USER_CONFIRMED",
            )
            vault.set_constraint(
                "demo.project", "database_queries", "writing database queries",
                "use async Motor and project only needed fields",
            )
            vault.set_summary("demo.project", "The demo service uses Postgres 16.")
            context = vault.context(
                "Which database does the demo service use?",
                provider="claude", namespace="demo.project", token_budget=120,
            )
            require("Postgres 16" in context["text"],
                    "relevant fact is compiled into provider context")
            require(estimate_tokens(context["text"]) <= 120,
                    "compiled context stays within the requested token budget")
            print("\nCompiled context preview:\n" + context["text"])
            print(f"Approx. tokens: {context['approx_tokens']} / {context['token_budget']}")

            raw_text = "DEMO RAW TRANSCRIPT: private deployment detail."
            sourced = vault.record(
                "demo.project", "deployment_host", "db.demo.internal",
                verification_state="USER_CONFIRMED", source_raw=raw_text,
            )
            safe_context = vault.context(
                "deployment host", provider="local", namespace="demo.project",
            )
            require("db.demo.internal" in safe_context["text"]
                    and "DEMO RAW TRANSCRIPT" not in safe_context["text"],
                    "raw source text stays out of compiled context")
            require(vault.drill_down(fact_id=sourced["id"])["raw_content"] == raw_text,
                    "raw source is available only through explicit drill-down")

            vault.record(
                "demo.security", "api_key", "DEMO_ONLY_fake_secret",
                sensitivity="SECRET", verification_state="USER_CONFIRMED",
            )
            try:
                vault.context("api key", provider="claude", namespace="demo.security")
            except LocalRoutingRequired as error:
                require(error.suggested_provider == "ollama",
                        "SECRET match blocks cloud context and recommends local routing")
            else:
                raise AssertionError("SECRET context unexpectedly reached a cloud provider")

            vault.record(
                "demo.confidential", "internal_host", "host.demo.internal",
                sensitivity="CONFIDENTIAL", verification_state="USER_CONFIRMED",
            )
            masked = vault.context(
                "internal host", provider="claude", namespace="demo.confidential",
            )
            require("host.demo.internal" not in masked["text"]
                    and bool(masked["redactions"]),
                    "CONFIDENTIAL values are masked for an untrusted provider")
            placeholder, original = next(iter(masked["redactions"].items()))
            restored = vault.rehydrate(f"The endpoint is {placeholder}.", masked["redactions"])
            require(original in restored,
                    "a masked value can be rehydrated before showing the response")

            vault.forget("demo.preferences", "editor")
            try:
                vault.record(
                    "demo.preferences", "editor", "Another editor",
                    verification_state="EXTRACTED",
                )
            except TombstonedSlot:
                passed("deleted slot stays deleted when extraction runs")
            else:
                raise AssertionError("extraction unexpectedly restored a deleted slot")
            vault.record(
                "demo.preferences", "editor", "Neovim",
                verification_state="USER_CONFIRMED",
            )
            passed("explicit user confirmation can restore a deleted slot")

        with MemtyLedger(path) as reopened:
            require(reopened.find("demo.project", "database")["value"] == "Postgres 16",
                    "facts persist after closing and reopening the SQLite database")
            require(reopened.list_constraints(namespace="demo.project")[0]["rule_id"]
                    == "database_queries",
                    "logical constraints persist after reopening")

        print("\nWeek 1 walkthrough passed. Temporary database cleaned up.")


if __name__ == "__main__":
    main()
