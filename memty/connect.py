"""Show connection instructions without reading or changing client settings."""
from __future__ import annotations

import os
import shlex
import sys


def _claude_command(executable: str) -> str:
    args = ["claude", "mcp", "add", "--scope", "user", "memty", "--",
            executable, "-m", "memty", "mcp"]
    if os.name == "nt":
        # PowerShell single-quoted strings treat two quotes as one literal quote.
        return " ".join("'" + arg.replace("'", "''") + "'" if index >= 6 else arg
                        for index, arg in enumerate(args))
    return shlex.join(args)


def connect_clients() -> dict:
    """Return setup information; never inspect or modify client configuration."""
    server = {"command": sys.executable, "args": ["-m", "memty", "mcp"]}
    return {
        "status": "instructions_only",
        "message": "No client configuration was read or changed. Choose a client below to connect Memty.",
        "server_entry": {"memty": server},
        "claude_code": {
            "command": _claude_command(sys.executable),
            "documentation": "https://code.claude.com/docs/en/mcp",
        },
        "claude_desktop": {"documentation": "https://modelcontextprotocol.io/quickstart/user"},
        "cursor": {"documentation": "https://docs.cursor.com/context/model-context-protocol"},
        "windsurf": {"documentation": "https://docs.windsurf.com/windsurf/cascade/mcp"},
        "note": "For client settings that accept JSON, add server_entry under mcpServers using the client's documented setup. Keep existing entries.",
    }
