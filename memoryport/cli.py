"""Manage a local Memty temporal vault without a web account or model API."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from getpass import getpass

from .factory import open_ledger
from .factory import default_vault_path
from .vault import export_nxvault, import_nxvault


def main() -> None:
    parser = argparse.ArgumentParser(prog="memty vault")
    parser.add_argument("--db", default=str(default_vault_path()))
    parser.add_argument("--user", default=os.getenv("MEMTY_MEMORY_USER", os.getenv("NEXORAI_MEMORY_USER", os.getenv("MEMTY_VAULT_USER", os.getenv("NEXOR_VAULT_USER", "local")))))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="list active and historical memories")
    add = commands.add_parser("add", help="save a user-confirmed fact")
    add.add_argument("namespace")
    add.add_argument("slot_key")
    add.add_argument("value")
    add.add_argument("--sensitivity", default="PERSONAL")
    add.add_argument("--allow-provider", action="append", default=[])
    add.add_argument("--block-provider", action="append", default=[])
    add.add_argument("--redact", action="store_true")
    recall = commands.add_parser("context", help="compile provider-filtered context")
    recall.add_argument("provider")
    recall.add_argument("query")
    recall.add_argument("--tokens", type=int, default=900)
    remove = commands.add_parser("delete", help="forget a memory by id")
    remove.add_argument("memory_id")
    approve = commands.add_parser("approve", help="approve a pending proposal")
    approve.add_argument("proposal_id")
    reject = commands.add_parser("reject", help="reject a pending proposal")
    reject.add_argument("proposal_id")
    commands.add_parser("proposals", help="list pending proposals")
    export = commands.add_parser("export", help="create a portable .nxvault file")
    export.add_argument("path")
    export.add_argument("--plaintext", action="store_true", help="allow an unencrypted export")
    imp = commands.add_parser("import", help="import a .nxvault file")
    imp.add_argument("path")
    imp.add_argument("--replace", action="store_true", help="replace this vault's ledger")
    evaluate = commands.add_parser("evaluate", help="run recall regression cases from a JSON file")
    evaluate.add_argument("cases")
    args = parser.parse_args()
    ledger = open_ledger(args.user, path=args.db)

    if args.command == "list":
        print(json.dumps(ledger.list(include_history=True), ensure_ascii=False, indent=2))
    elif args.command == "add":
        result = ledger.record(args.namespace, args.slot_key, args.value,
                               verification_state="USER_CONFIRMED", sensitivity_tier=args.sensitivity,
                               allowed_providers=args.allow_provider, blocked_providers=args.block_provider,
                               ephemeral_redaction=args.redact)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "context":
        print(json.dumps(ledger.context(args.query, provider=args.provider, token_budget=args.tokens),
                         ensure_ascii=False, indent=2))
    elif args.command == "delete":
        result = ledger.delete(args.memory_id)
        if result is None:
            raise SystemExit("Memory not found or already deleted.")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "proposals":
        print(json.dumps(ledger.proposals(), ensure_ascii=False, indent=2))
    elif args.command in {"approve", "reject"}:
        result = ledger.resolve_proposal(args.proposal_id, approve=args.command == "approve")
        if result is None:
            raise SystemExit("Proposal not found or already resolved.")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "export":
        passphrase = None if args.plaintext else getpass("Vault passphrase (min 10 characters): ")
        path = export_nxvault(ledger, args.path, passphrase=passphrase, allow_plaintext=args.plaintext)
        print(path)
    elif args.command == "import":
        passphrase = getpass("Vault passphrase (leave empty for plaintext): ") or None
        count = import_nxvault(ledger, args.path, passphrase=passphrase, merge=not args.replace)
        print(f"Imported {count} ledger events.")
    elif args.command == "evaluate":
        from .evaluation import evaluate_cases
        with open(args.cases, "r", encoding="utf-8") as handle:
            cases = json.load(handle)
        if not isinstance(cases, list):
            raise SystemExit("Evaluation file must contain a JSON list of cases.")
        print(json.dumps(evaluate_cases(ledger, cases), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

