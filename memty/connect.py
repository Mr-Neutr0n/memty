"""Connect Memty to AI clients without ever writing their settings files.

Editing another application's config file is risky: a bad write, an
encoding mismatch, or a race with the running app can leave the client unable
to start. ``memty connect`` therefore never creates, modifies, or deletes any
client file. It only hands the change to each client's own supported installer:

* **Claude Code**: runs Claude Code's official ``claude mcp add`` command,
  so Claude Code validates and saves its own settings.
* **Cursor**: opens Cursor's official MCP install link. Cursor asks the user
  to confirm before it adds the server.
* **Claude Desktop / Windsurf**: these have no supported installer Memty can
  call, so Memty prints the exact entry and where to add it.

Client files are only *read*, to report whether Memty is already connected.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from urllib.parse import quote

SERVER_NAME = "memty"
CLIENTS = ("Claude Desktop", "Claude Code", "Cursor", "Windsurf")


def server_entry(executable: str | None = None) -> dict:
    return {"command": executable or sys.executable, "args": ["-m", "memty", "mcp"]}


def _claude_desktop_path(home: Path) -> Path:
    if sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming")))
        standard = appdata / "Claude"
        # The Microsoft Store (MSIX) build keeps its settings in a virtualized folder.
        local = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
        if not standard.is_dir() and (local / "Packages").is_dir():
            for package in sorted((local / "Packages").glob("Claude_*")):
                packaged = package / "LocalCache" / "Roaming" / "Claude"
                if packaged.is_dir():
                    return packaged / "claude_desktop_config.json"
        return standard / "claude_desktop_config.json"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    config = Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config")))
    return config / "Claude" / "claude_desktop_config.json"


def client_paths(home: Path | None = None) -> dict[str, Path]:
    home = Path(home) if home is not None else Path.home()
    return {
        "Claude Desktop": _claude_desktop_path(home),
        "Claude Code": home / ".claude.json",
        "Cursor": home / ".cursor" / "mcp.json",
        "Windsurf": home / ".codeium" / "windsurf" / "mcp_config.json",
    }


def _detected(name: str, path: Path, claude_cli: str | None) -> bool:
    if path.exists():
        return True
    if name == "Claude Code":
        # The home directory always exists, so only the file or the CLI counts.
        return claude_cli is not None
    # The app creates its settings folder on first launch.
    return path.parent.is_dir()


def _matches(current, entry: dict) -> bool:
    """True when an existing entry already launches the same server."""
    return isinstance(current, dict) and all(current.get(key) == value for key, value in entry.items())


def _current_entry(path: Path):
    """Read-only lookup of an existing memty entry; never raises, never writes."""
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
        servers = config.get("mcpServers") if isinstance(config, dict) else None
        return servers.get(SERVER_NAME) if isinstance(servers, dict) else None
    except (OSError, ValueError):
        return None


def cursor_install_link(entry: dict) -> str:
    """Cursor's documented install link: name plus base64 of the server JSON."""
    payload = base64.b64encode(json.dumps(entry, separators=(",", ":")).encode("utf-8")).decode("ascii")
    return ("cursor://anysphere.cursor-deeplink/mcp/install?name=" + quote(SERVER_NAME)
            + "&config=" + quote(payload, safe=""))


def _open_url(url: str) -> None:
    """Hand a URL to the operating system, which routes it to the owning app."""
    if sys.platform == "win32":
        os.startfile(url)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", url], check=True, timeout=30)
    else:
        subprocess.run(["xdg-open", url], check=True, timeout=30)


def _claude_command(executable: str) -> str:
    args = ["claude", "mcp", "add", "--scope", "user", SERVER_NAME, "--",
            executable, "-m", "memty", "mcp"]
    if os.name == "nt":
        # PowerShell single-quoted strings treat two quotes as one literal quote.
        return " ".join("'" + arg.replace("'", "''") + "'" if index >= 6 else arg
                        for index, arg in enumerate(args))
    return shlex.join(args)


def _manual(name: str, path: Path, entry: dict) -> dict:
    steps = {
        "Claude Desktop": "In Claude Desktop open Settings > Developer > Edit Config, add the "
                          "entry under mcpServers (keep existing entries), save, and restart Claude.",
        "Windsurf": "In Windsurf open the MCP settings and choose the option to view or edit the "
                    "raw config, add the entry under mcpServers (keep existing entries), then refresh.",
    }[name]
    return {"status": "manual_step", "path": str(path), "steps": steps,
            "entry": {"mcpServers": {SERVER_NAME: entry}}}


def _connect_claude_code(path: Path, entry: dict, claude_cli: str | None, dry_run: bool) -> dict:
    manual = _claude_command(entry["command"])
    result = {"path": str(path), "method": "claude mcp add"}
    current = _current_entry(path)
    if _matches(current, entry):
        return {**result, "status": "already_connected"}
    if claude_cli is None:
        return {"status": "manual_step", "path": str(path),
                "steps": "Install the Claude Code CLI, or run this command where it is available.",
                "command": manual}
    action = "update" if current is not None else "add"
    if dry_run:
        return {**result, "status": "would_" + action}
    try:
        # Claude Code's own CLI validates and saves its settings; Memty never edits the file.
        if current is not None:
            subprocess.run([claude_cli, "mcp", "remove", "--scope", "user", SERVER_NAME],
                           capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        proc = subprocess.run([claude_cli, "mcp", "add", "--scope", "user", SERVER_NAME, "--",
                               entry["command"], *entry["args"]],
                              capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as error:
        return {**result, "status": "error", "error": str(error), "command": manual}
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip() or f"claude exited with {proc.returncode}"
        return {**result, "status": "error", "error": detail, "command": manual}
    return {**result, "status": "updated" if action == "update" else "connected"}


def _connect_cursor(path: Path, entry: dict, dry_run: bool, open_links: bool) -> dict:
    link = cursor_install_link(entry)
    result = {"path": str(path), "method": "cursor install link", "link": link}
    if _matches(_current_entry(path), entry):
        return {"path": str(path), "method": "cursor install link", "status": "already_connected"}
    if dry_run:
        return {**result, "status": "would_open_install_prompt"}
    if not open_links:
        return {**result, "status": "manual_step",
                "steps": "Open the link; Cursor asks you to confirm the install."}
    try:
        _open_url(link)
    except (OSError, subprocess.SubprocessError) as error:
        return {**result, "status": "manual_step", "error": str(error),
                "steps": "Could not open Cursor automatically. Open the link; Cursor asks you to confirm."}
    return {**result, "status": "install_prompt_opened",
            "steps": "Confirm the install in Cursor."}


def connect_clients(paths: dict[str, Path] | None = None, *, dry_run: bool = False,
                    clients: list[str] | None = None, claude_cli: str | None | bool = True,
                    executable: str | None = None, open_links: bool = True) -> dict:
    """Connect detected clients through their own installers; never write their files.

    ``claude_cli=True`` looks the ``claude`` executable up on PATH; pass a path
    to use a specific one, or ``None`` to skip running it.
    """
    if claude_cli is True:
        claude_cli = shutil.which("claude")
    claude_cli = claude_cli or None
    entry = server_entry(executable)
    wanted = {name.casefold() for name in clients} if clients else None
    results = {}
    for name, path in (paths if paths is not None else client_paths()).items():
        if wanted is not None and name.casefold() not in wanted:
            continue
        path = Path(path)
        if not _detected(name, path, claude_cli):
            results[name] = {"status": "not_detected", "path": str(path)}
        elif name == "Claude Code":
            results[name] = _connect_claude_code(path, entry, claude_cli, dry_run)
        elif name == "Cursor":
            results[name] = _connect_cursor(path, entry, dry_run, open_links)
        elif _matches(_current_entry(path), entry):
            results[name] = {"status": "already_connected", "path": str(path)}
        else:
            results[name] = _manual(name, path, entry)

    statuses = {r["status"] for r in results.values()}
    if "error" in statuses:
        next_step = "A client installer reported an error; see its entry above."
    elif dry_run and statuses & {"would_add", "would_update", "would_open_install_prompt"}:
        next_step = "Run memty connect without --dry-run to apply."
    elif statuses & {"connected", "updated", "install_prompt_opened", "manual_step"}:
        next_step = "Finish any manual steps above, then restart the connected clients."
    elif statuses <= {"not_detected"}:
        next_step = "No supported client was detected. Add server_entry using your client's MCP settings."
    else:
        next_step = "Memty is already connected; no changes were needed."
    return {
        "dry_run": dry_run,
        "clients": results,
        "server_entry": {SERVER_NAME: entry},
        "manual_claude_code_command": _claude_command(entry["command"]),
        "note": "Memty never writes client settings files. Changes are made by each client's own installer or by you.",
        "next_step": next_step,
    }
