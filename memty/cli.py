"""Small standard-library CLI for inspecting and operating a Memty vault."""

from __future__ import annotations

import argparse
import json
import sys

from .compiler import LocalRoutingRequired
from .factory import default_user_id, default_vault_path
from .ledger import MemtyLedger


def _print(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _ledger(args) -> MemtyLedger:
    trusted = [item.strip() for item in (args.trusted_provider or []) if item.strip()]
    from .daemon import DaemonLedger
    return DaemonLedger(args.db, args.user, trusted_providers=trusted)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "daemon":
        from .daemon import main as daemon_main
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        daemon_main()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "mcp":
        from .mcp_server import main as mcp_main
        mcp_main()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "vault":
        from .legacy_vault import main as legacy_vault_main
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        legacy_vault_main()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "api":
        from .api import main as api_main
        api_main()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "router-mcp":
        from .router_mcp import main as router_mcp_main
        router_mcp_main()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "vault-mcp":
        from .legacy_mcp import main as legacy_mcp_main
        legacy_mcp_main()
        return
    if len(sys.argv) > 1 and sys.argv[1] in {"init", "models", "route", "chat", "integration"}:
        from memoryport.sdk_cli import main as sdk_main
        sdk_main()
        return
    parser = argparse.ArgumentParser(
        prog="memty",
        description="Memty model routing, chat, and user-owned memory tools",
        epilog="Also available: init, models, route, chat, integration, vault, api, router-mcp, vault-mcp.",
    )
    parser.add_argument("--db", default=str(default_vault_path()))
    parser.add_argument("--user", default=default_user_id())
    parser.add_argument("--trusted-provider", action="append", default=[],
                        help="Cloud provider allowed to see CONFIDENTIAL facts without redaction")
    commands = parser.add_subparsers(dest="command", required=True)

    remember = commands.add_parser("remember", help="save or supersede one atomic fact")
    remember.add_argument("namespace")
    remember.add_argument("slot")
    remember.add_argument("value")
    remember.add_argument("--confidence", type=float, default=1.0)
    remember.add_argument("--sensitivity", default="PUBLIC",
                          choices=["PUBLIC", "INTERNAL", "CONFIDENTIAL", "SECRET"])
    remember.add_argument("--verification", default="USER_CONFIRMED",
                          choices=["USER_CONFIRMED", "SPEC_LOCKED", "EXTRACTED"])
    remember.add_argument("--allow-provider", action="append", default=[])
    remember.add_argument("--block-provider", action="append", default=[])
    remember.add_argument("--ephemeral-redaction", action="store_true")
    remember.add_argument("--raw", help="raw source text to archive for explicit drill-down")

    recall = commands.add_parser("recall", help="compile context within a token budget")
    recall.add_argument("query")
    recall.add_argument("--provider", default="local")
    recall.add_argument("--tokens", type=int, default=600)
    recall.add_argument("--namespace")

    forget = commands.add_parser("forget", help="tombstone a slot and purge its audit history")
    forget.add_argument("namespace")
    forget.add_argument("slot")
    forget.add_argument("--purge-raw", action="store_true")

    listing = commands.add_parser("list", help="list active facts")
    listing.add_argument("--namespace")
    listing.add_argument("--all", action="store_true", help="include tombstones")

    summary = commands.add_parser("summary", help="read or set a namespace summary")
    summary.add_argument("namespace")
    summary.add_argument("--set", dest="summary_text")
    summary.add_argument("--max-tokens", type=int, default=150)

    rule = commands.add_parser("rule", help="create or replace a logical namespace rule")
    rule.add_argument("namespace")
    rule.add_argument("rule_id")
    rule.add_argument("if_condition")
    rule.add_argument("then_constraint")

    rules = commands.add_parser("rules", help="list logical namespace rules")
    rules.add_argument("--namespace")

    rule_delete = commands.add_parser("rule-delete", help="delete a logical namespace rule")
    rule_delete.add_argument("namespace")
    rule_delete.add_argument("rule_id")

    commands.add_parser("stats", help="show vault counters and paths")
    commands.add_parser("connect", help="show safe MCP client setup instructions")

    raw_add = commands.add_parser("raw-add", help="archive raw text without changing facts")
    raw_add.add_argument("namespace")
    raw_add.add_argument("content")

    raw_get = commands.add_parser("raw-get", help="explicitly fetch an archived raw document")
    raw_get.add_argument("raw_id")

    history = commands.add_parser("history", help="show superseded versions for one slot")
    history.add_argument("namespace")
    history.add_argument("slot")

    migrate = commands.add_parser("migrate", help="import facts from a previous Memty temporal vault")
    migrate.add_argument("path")

    args = parser.parse_args()
    if args.command == "connect":
        from .connect import connect_clients
        results = connect_clients()
        _print(results)
        return
    ledger = _ledger(args)

    if args.command == "remember":
        result = ledger.record(
            args.namespace, args.slot, args.value, confidence=args.confidence,
            verification_state=args.verification, sensitivity=args.sensitivity,
            allowed_providers=args.allow_provider, blocked_providers=args.block_provider,
            ephemeral_redaction=args.ephemeral_redaction, source_raw=args.raw,
        )
        _print(result)
    elif args.command == "recall":
        try:
            _print(ledger.context(args.query, provider=args.provider,
                                  token_budget=args.tokens, namespace=args.namespace))
        except LocalRoutingRequired as error:
            _print(error.as_dict())
            raise SystemExit(2)
    elif args.command == "forget":
        result = ledger.forget(args.namespace, args.slot, purge_raw=args.purge_raw)
        if result is None:
            raise SystemExit("slot not found")
        _print(result)
    elif args.command == "list":
        _print(ledger.list(namespace=args.namespace, include_tombstones=args.all))
    elif args.command == "summary":
        if args.summary_text is not None:
            _print(ledger.set_summary(args.namespace, args.summary_text))
        elif ledger.summary(args.namespace) is not None:
            _print(ledger.summary(args.namespace))
        else:
            _print(ledger.summarize_namespace(args.namespace, max_tokens=args.max_tokens))
    elif args.command == "rule":
        _print(ledger.set_constraint(args.namespace, args.rule_id,
                                     args.if_condition, args.then_constraint))
    elif args.command == "rules":
        _print(ledger.list_constraints(namespace=args.namespace))
    elif args.command == "rule-delete":
        _print({"deleted": ledger.delete_constraint(args.namespace, args.rule_id),
                "namespace": args.namespace, "rule_id": args.rule_id})
    elif args.command == "stats":
        _print(ledger.stats())
    elif args.command == "raw-add":
        _print({"raw_id": ledger.archive_raw(args.namespace, args.content)})
    elif args.command == "raw-get":
        result = ledger.drill_down(args.raw_id)
        if result is None:
            raise SystemExit("raw document not found")
        _print(result)
    elif args.command == "history":
        _print(ledger.history(args.namespace, args.slot))
    elif args.command == "migrate":
        from .migrate import migrate_from_legacy
        _print(migrate_from_legacy(args.path, ledger))
    else:  # pragma: no cover - argparse enforces the command list
        parser.error("unknown command")


if __name__ == "__main__":
    main()
