"""Small standard-library CLI for inspecting and operating a Memty vault."""

from __future__ import annotations

import argparse
import json
from importlib import metadata
import sys

from .compiler import LocalRoutingRequired
from .factory import default_user_id, default_vault_path
from .ledger import MemtyLedger


def _version() -> str:
    """Read the installed distribution version without starting the vault."""
    try:
        return metadata.version("memty")
    except metadata.PackageNotFoundError:
        return "development"


def _welcome() -> None:
    """Show a portable, read-only introduction when no command is supplied."""
    wordmark = r"""
   __  __  _____  __  __  _____ __   __
  |  \/  || ____||  \/  ||_   _|\ \ / /
  | |\/| ||  _|  | |\/| |  | |   \ V /
  | |  | || |___ | |  | |  | |    | |
  |_|  |_||_____||_|  |_|  |_|    |_|
""".strip("\n")
    print(wordmark)
    print(f"""
  Local memory for AI assistants  |  v{_version()}
  ------------------------------------------------------------

  Memty keeps your facts, decisions, and context in a
  user-owned local vault. Connect supported assistants to
  share relevant memory through the MCP bridge.

  GET STARTED

  memty connect      Connect your AI assistants
  memty remember     Save a fact to your vault
  memty recall       Retrieve relevant context
  memty clip NS      Copy a namespace capsule for any AI
  memty serve        Bridge browser assistants (127.0.0.1)
  memty stats        View vault statistics
  memty --help       See all commands

  TRY IT

  memty remember project.demo editor "VS Code"
  memty recall "editor" --namespace project.demo

  ------------------------------------------------------------
  Your memory stays under your control.
""".strip("\n"))


def _print(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _ledger(args) -> MemtyLedger:
    trusted = [item.strip() for item in (args.trusted_provider or []) if item.strip()]
    from .daemon import DaemonLedger
    return DaemonLedger(args.db, args.user, trusted_providers=trusted)


def _serve(args) -> None:
    from . import web_bridge
    if args.stop:
        _print(web_bridge.stop_background(args.db))
        return
    token = web_bridge.load_or_create_token(args.db, rotate=args.new_token)
    if args.show_token or args.new_token:
        print(token)
        return
    if args.background:
        _print({**web_bridge.start_background(args.db, args.user, port=args.port,
                                              allowed_origins=args.allow_origin),
                "url": f"http://127.0.0.1:{args.port}",
                "pair": "Paste the token from `memty serve --show-token` into the extension options."})
        return
    print(f"Memty bridge on http://127.0.0.1:{args.port} (Ctrl+C to stop)", file=sys.stderr)
    print("Pairing token (paste into the extension options): " + token, file=sys.stderr)
    try:
        web_bridge.serve(args.db, args.user, port=args.port, allowed_origins=args.allow_origin,
                         quiet=not args.verbose)
    except OSError as error:
        raise SystemExit(f"Could not listen on 127.0.0.1:{args.port}: {error}")


def _clip(args, ledger) -> None:
    try:
        result = ledger.context(args.query, provider=args.provider, namespace=args.namespace,
                                token_budget=args.tokens, strict_namespace=True)
    except LocalRoutingRequired as error:
        _print(error.as_dict())
        raise SystemExit(2)
    text = result["text"]
    if not text:
        raise SystemExit(f"No facts to share in namespace '{args.namespace}'.")
    if args.print_only:
        print(text)
        return
    from .clipboard import copy_text
    try:
        copy_text(text)
    except Exception as error:  # clipboard tool missing or failed: never lose the capsule
        print(text)
        raise SystemExit(f"Could not copy to the clipboard ({error}); the capsule is printed above.")
    redacted = len(result.get("redactions") or {})
    note = f", {redacted} confidential value(s) redacted" if redacted else ""
    print(f"Copied {args.namespace} capsule (~{result['approx_tokens']} tokens{note}). Paste it into any AI.",
          file=sys.stderr)


def main() -> None:
    if len(sys.argv) == 1:
        _welcome()
        return
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
        description="Memty: a user-owned local memory vault for AI assistants",
        epilog="Also available: init, models, route, chat, integration, vault, api, router-mcp, vault-mcp.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_version()}")
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
    connect = commands.add_parser(
        "connect", help="connect Memty to Claude Desktop, Claude Code, Cursor, and Windsurf",
        description="Connect Memty through each client's own installer. Memty never writes client "
                    "settings files: Claude Code uses 'claude mcp add', Cursor shows its install prompt, "
                    "and Claude Desktop and Windsurf get exact manual steps.")
    connect.add_argument("--dry-run", action="store_true", help="show the plan without running anything")
    connect.add_argument("--no-open", action="store_true",
                         help="print the Cursor install link instead of opening it")
    connect.add_argument("--client", action="append", choices=["Claude Desktop", "Claude Code", "Cursor", "Windsurf"],
                         help="only connect this client (repeatable)")

    serve = commands.add_parser(
        "serve", help="run the localhost bridge for browser assistants (127.0.0.1 only)",
        description="Serve capsules to the Memty browser extension on 127.0.0.1. "
                    "Requests need the pairing token and an extension origin.")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--allow-origin", action="append", default=[],
                       help="only accept this origin, e.g. chrome-extension://<id> (repeatable)")
    serve.add_argument("--background", action="store_true", help="start quietly in the background")
    serve.add_argument("--stop", action="store_true", help="stop a background bridge")
    serve.add_argument("--show-token", action="store_true", help="print the pairing token and exit")
    serve.add_argument("--new-token", action="store_true",
                       help="replace the pairing token (re-pair the extension afterwards)")
    serve.add_argument("--verbose", action="store_true", help="log request paths (never bodies)")

    clip = commands.add_parser("clip", help="copy a namespace capsule to the clipboard for any AI")
    clip.add_argument("namespace")
    clip.add_argument("--query", default="", help="rank facts for this question")
    clip.add_argument("--provider", default="clipboard",
                      help="who will read it; non-local providers get CONFIDENTIAL values redacted")
    clip.add_argument("--tokens", type=int, default=200)
    clip.add_argument("--print", dest="print_only", action="store_true",
                      help="print the capsule instead of copying it")

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
        results = connect_clients(dry_run=args.dry_run, clients=args.client,
                                  open_links=not args.no_open)
        _print(results)
        if any(item["status"] == "error" for item in results["clients"].values()):
            raise SystemExit(1)
        return
    if args.command == "serve":
        _serve(args)
        return
    ledger = _ledger(args)
    if args.command == "clip":
        _clip(args, ledger)
        return

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
