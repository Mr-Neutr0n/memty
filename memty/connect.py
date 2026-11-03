"""Install Memty's stdio MCP entry into detected client configurations."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile


def client_paths(home: Path | None = None) -> dict[str, Path]:
    home = home or Path.home()
    if sys.platform == "win32":
        desktop = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming"))) / "Claude"
    elif sys.platform == "darwin":
        desktop = home / "Library" / "Application Support" / "Claude"
        # Create the directory if it doesn't exist
        #desktop.mkdir(parents=True, exists_ok=True)
    else:
        desktop = Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config"))) / "Claude"
    return {
        "Claude Desktop": desktop / "claude_desktop_config.json",
        "Claude Code": home / ".claude.json",
        "Cursor": home / ".cursor" / "mcp.json",
        "Windsurf": home / ".codeium" / "windsurf" / "mcp_config.json",
    }


def connect_clients(paths: dict[str, Path] | None = None) -> dict:
    results = {}
    for name, path in (paths if paths is not None else client_paths()).items():
        path = Path(path)
        # Claude Code's config lives directly in the home directory; a home
        # directory alone is not evidence that Claude Code is installed.
        detected = path.exists() or (name != "Claude Code" and path.parent.is_dir())
        if not detected:
            results[name] = {"status": "not_detected", "path": str(path)}
            continue
        temp_name = None
        try:
            config = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
            if not isinstance(config, dict):
                raise ValueError("configuration must be a JSON object")
            servers = config.setdefault("mcpServers", {})
            if not isinstance(servers, dict):
                raise ValueError("mcpServers must be a JSON object")
            servers["memty"] = {"command": sys.executable, "args": ["-m", "memty", "mcp"]}
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             delete=False, newline="\n") as tmp:
                temp_name = tmp.name
                json.dump(config, tmp, ensure_ascii=False, indent=2)
                tmp.write("\n")
            os.replace(temp_name, path)
            results[name] = {"status": "connected", "path": str(path)}
        except (OSError, ValueError) as error:
            results[name] = {"status": "error", "path": str(path), "error": str(error)}
        finally:
            if temp_name and os.path.exists(temp_name):
                os.unlink(temp_name)
    return results
