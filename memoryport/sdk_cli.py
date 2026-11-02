"""Model-routing and chat commands for the Memty CLI."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .sdk import ConfigurationError, Memty, load_client


def _config_arg(parser: argparse.ArgumentParser) -> None:
    default_config = Path.home() / ".memty" / "models.json"
    legacy_config = Path.home() / ".nexorai" / "models.json"
    if not default_config.exists() and legacy_config.exists():
        default_config = legacy_config
    parser.add_argument("--config", default=os.getenv("MEMTY_CONFIG", os.getenv("NEXORAI_CONFIG", str(default_config))),
                        help="model catalog JSON (default: ~/.memty/models.json)")


def _integration(client: str) -> str:
    command = f'"{sys.executable}" -m memty.router_mcp'
    if client == "codex":
        return f"codex mcp add memty -- {command}"
    if client == "claude-code":
        return f"claude mcp add --scope user memty -- {command}"
    return json.dumps({"servers": {"memty": {"type": "stdio", "command": sys.executable,
                                                 "args": ["-m", "memty.router_mcp"]}}}, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(prog="memty", description="Route prompts across configured local and cloud model providers.")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="write a sample local model catalog")
    init.add_argument("--path", default=str(Path.home() / ".memty" / "models.json"))

    models = commands.add_parser("models", help="list configured models and credential readiness")
    _config_arg(models)

    route = commands.add_parser("route", help="recommend a model without sending the prompt anywhere")
    route.add_argument("prompt", nargs="+")
    route.add_argument("--strategy", choices=("adaptive", "rules", "cheapest", "fastest"))
    _config_arg(route)

    chat = commands.add_parser("chat", help="send one prompt or open a multi-turn local chat")
    chat.add_argument("prompt", nargs="*")
    chat.add_argument("--chat-id", default="cli")
    chat.add_argument("--model", default="auto", help="auto or a model id")
    chat.add_argument("--interactive", action="store_true", help="keep this chat in memory until exit")
    chat.add_argument("--strategy", choices=("adaptive", "rules", "cheapest", "fastest"))
    _config_arg(chat)

    integrations = commands.add_parser("integration", help="show setup for coding agents that support MCP")
    integrations.add_argument("client", choices=("codex", "claude-code", "vscode"))

    args = parser.parse_args()
    try:
        if args.command == "init":
            print(Memty.default_config(args.path))
            return
        if args.command == "integration":
            print(_integration(args.client))
            return
        client = load_client(args.config, routing=getattr(args, "strategy", None) or "adaptive")
        if args.command == "models":
            print(json.dumps(client.list_models(), indent=2))
            return
        if args.command == "route":
            result = client.route(" ".join(args.prompt), strategy=args.strategy)
            print(json.dumps({**result.__dict__, "alternatives": list(result.alternatives)}, indent=2))
            return
        if args.command == "chat":
            if args.interactive:
                print("Memty chat. Enter /exit to quit, /clear to clear this chat.")
                while True:
                    try:
                        prompt = input("you> ").strip()
                    except (EOFError, KeyboardInterrupt):
                        print()
                        break
                    if prompt == "/exit":
                        break
                    if prompt == "/clear":
                        client.clear_chat(args.chat_id)
                        print("Chat cleared.")
                        continue
                    if not prompt:
                        continue
                    response = client.chat(prompt, chat_id=args.chat_id, model_id=args.model,
                                           strategy=args.strategy)
                    print(f"\n{response.text}\n\n[{response.model_id} · {response.latency_ms} ms]\n")
                return
            if not args.prompt:
                parser.error("chat requires a prompt or --interactive")
            response = client.chat(" ".join(args.prompt), chat_id=args.chat_id,
                                   model_id=args.model, strategy=args.strategy)
            print(response.text)
            return
    except (ConfigurationError, OSError, ValueError, RuntimeError) as error:
        print(f"memty: {error}", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()

