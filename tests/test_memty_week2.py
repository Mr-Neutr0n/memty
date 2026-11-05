"""Integration coverage for concurrent storage and the MCP bridge."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from memty.connect import connect_clients
from memty.ledger import MemtyLedger
from memty.tokens import estimate_tokens


class WeekTwoTests(unittest.TestCase):
    def test_parallel_connections_and_pragmas(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.sqlite3"
            with MemtyLedger(path) as ledger:
                with ledger._connect() as db:
                    self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
                    self.assertEqual(db.execute("PRAGMA busy_timeout").fetchone()[0], 5000)
                    self.assertEqual(db.execute("PRAGMA synchronous").fetchone()[0], 1)
            def worker(i):
                with MemtyLedger(path) as ledger:
                    for j in range(15):
                        ledger.record("parallel", f"slot_{i}_{j}", "value")
                        ledger.context("value", provider="local", namespace="parallel")
            with ThreadPoolExecutor(max_workers=5) as pool:
                list(pool.map(worker, range(5)))
            with MemtyLedger(path) as ledger:
                self.assertEqual(ledger.stats()["active_facts"], 75)

    def test_independent_processes_share_ledger(self):
        import subprocess, sys
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "ledger.sqlite3")
            with MemtyLedger(path):
                pass
            code = """import sys
from memty.ledger import MemtyLedger
with MemtyLedger(sys.argv[1]) as ledger:
    for i in range(20):
        ledger.record('processes', 'p' + sys.argv[2] + '_' + str(i), 'value')
        ledger.context('value', provider='local', namespace='processes')
"""
            processes = [subprocess.Popen([sys.executable, "-c", code, path, str(i)],
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                         for i in range(4)]
            for process in processes:
                stdout, stderr = process.communicate(timeout=30)
                self.assertEqual(process.returncode, 0, (stdout, stderr))
            with MemtyLedger(path) as ledger:
                self.assertEqual(ledger.stats()["active_facts"], 80)

    def test_daemon_shared_by_cli_clients_and_restart(self):
        import subprocess, sys
        from memty.daemon import status, stop
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "daemon.sqlite3")
            try:
                processes = [subprocess.Popen(
                    [sys.executable, "-m", "memty", "--db", path, "remember", "shared",
                     "slot_" + str(i), "value"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    for i in range(4)]
                for process in processes:
                    out, err = process.communicate(timeout=35)
                    self.assertEqual(process.returncode, 0, (out, err))
                first = status(path)
                self.assertTrue(first["running"])
                proc = subprocess.run([sys.executable, "-m", "memty", "--db", path, "stats"],
                                      capture_output=True, text=True, timeout=15)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(json.loads(proc.stdout)["active_facts"], 4)
                self.assertEqual(status(path)["pid"], first["pid"])
                self.assertTrue(stop(path)["stopped"])
                self.assertFalse(status(path)["running"])
                proc = subprocess.run([sys.executable, "-m", "memty", "--db", path, "stats"],
                                      capture_output=True, text=True, timeout=20)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(json.loads(proc.stdout)["active_facts"], 4)
                self.assertTrue(status(path)["running"])
            finally:
                stop(path)

    def test_daemon_rejects_unauthenticated_requests(self):
        from memty.daemon import _exchange, ensure_daemon, stop
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "daemon.sqlite3")
            try:
                endpoint = ensure_daemon(path)
                with self.assertRaisesRegex(RuntimeError, "credentials"):
                    _exchange({**endpoint, "token": "wrong"}, {"method": "stats"})
            finally:
                stop(path)

    def _client_home(self, tmp):
        home = Path(tmp)
        paths = {
            "Claude Desktop": home / "appdata" / "Claude" / "claude_desktop_config.json",
            "Claude Code": home / ".claude.json",
            "Cursor": home / ".cursor" / "mcp.json",
            "Windsurf": home / ".codeium" / "windsurf" / "mcp_config.json",
        }
        return home, paths

    def test_connect_injects_into_every_detected_client_and_keeps_existing_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, paths = self._client_home(tmp)
            # Desktop: folder only (fresh install). Code: existing settings.
            # Cursor: another server plus a BOM. Windsurf: not installed.
            paths["Claude Desktop"].parent.mkdir(parents=True)
            paths["Claude Code"].write_text('{"numStartups": 3, "projects": {"x": {}}}', encoding="utf-8")
            paths["Cursor"].parent.mkdir(parents=True)
            original_cursor = '﻿{"mcpServers": {"other": {"command": "node"}}, "theme": "dark"}'
            paths["Cursor"].write_text(original_cursor, encoding="utf-8")
            result = connect_clients(paths, claude_cli=None, executable="/py")["clients"]

            self.assertEqual(result["Claude Desktop"]["status"], "connected")
            self.assertIsNone(result["Claude Desktop"]["backup"])
            self.assertEqual(result["Claude Code"]["status"], "connected")
            self.assertEqual(result["Cursor"]["status"], "connected")
            self.assertEqual(result["Windsurf"]["status"], "not_detected")
            self.assertFalse(paths["Windsurf"].parent.exists())

            entry = {"command": "/py", "args": ["-m", "memty", "mcp"]}
            for name in ("Claude Desktop", "Claude Code", "Cursor"):
                config = json.loads(paths[name].read_text(encoding="utf-8"))
                self.assertEqual(config["mcpServers"]["memty"], entry)
            code = json.loads(paths["Claude Code"].read_text(encoding="utf-8"))
            self.assertEqual((code["numStartups"], code["projects"]), (3, {"x": {}}))
            cursor = json.loads(paths["Cursor"].read_text(encoding="utf-8"))
            self.assertEqual(cursor["mcpServers"]["other"], {"command": "node"})
            self.assertEqual(cursor["theme"], "dark")
            backup = Path(result["Cursor"]["backup"])
            self.assertEqual(backup.read_text(encoding="utf-8"), original_cursor)

            # Running again changes nothing and makes no new backups.
            before = sorted(Path(tmp).rglob("*"))
            again = connect_clients(paths, claude_cli=None, executable="/py")["clients"]
            self.assertEqual({r["status"] for n, r in again.items() if n != "Windsurf"},
                             {"already_connected"})
            self.assertEqual(before, sorted(Path(tmp).rglob("*")))

            # A stale interpreter path is updated in place, with a backup.
            moved = connect_clients(paths, claude_cli=None, executable="/new-py",
                                    clients=["cursor"])["clients"]
            self.assertEqual(list(moved), ["Cursor"])
            self.assertEqual(moved["Cursor"]["status"], "updated")
            self.assertTrue(Path(moved["Cursor"]["backup"]).exists())
            self.assertEqual(json.loads(paths["Cursor"].read_text(encoding="utf-8"))
                             ["mcpServers"]["memty"]["command"], "/new-py")

    def test_connect_never_overwrites_invalid_config_and_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, paths = self._client_home(tmp)
            bad = {"Cursor": b"{invalid", "Windsurf": b'{"mcpServers": []}',
                   "Claude Code": b"[1, 2]"}
            for name, data in bad.items():
                paths[name].parent.mkdir(parents=True, exist_ok=True)
                paths[name].write_bytes(data)
            paths["Claude Desktop"].parent.mkdir(parents=True)

            def snapshot():
                return {p: p.read_bytes() for p in Path(tmp).rglob("*") if p.is_file()}
            before = snapshot()

            plan = connect_clients(paths, claude_cli=None, dry_run=True)
            self.assertTrue(plan["dry_run"])
            self.assertEqual(plan["clients"]["Claude Desktop"]["status"], "would_add")
            self.assertEqual(before, snapshot())

            result = connect_clients(paths, claude_cli=None)["clients"]
            for name in bad:
                self.assertEqual(result[name]["status"], "error")
                self.assertIn("not changed", result[name]["error"])
            self.assertEqual(result["Claude Desktop"]["status"], "connected")
            paths["Claude Desktop"].unlink()
            self.assertEqual(before, snapshot())

    def test_connect_uses_claude_cli_when_available(self):
        from unittest.mock import patch
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            _, paths = self._client_home(tmp)
            paths["Claude Code"].write_text(json.dumps({"mcpServers": {"memty": {
                "type": "stdio", "command": "/old", "args": ["-m", "memty", "mcp"], "env": {}}}}),
                encoding="utf-8")
            before = paths["Claude Code"].read_bytes()
            calls = []

            def fake_run(cmd, **kwargs):
                calls.append(cmd)
                return subprocess.CompletedProcess(cmd, 0, "", "")
            with patch("memty.connect.subprocess.run", side_effect=fake_run):
                result = connect_clients({"Claude Code": paths["Claude Code"]},
                                         claude_cli="claude", executable="/py")["clients"]
            self.assertEqual(result["Claude Code"], {"path": str(paths["Claude Code"]),
                             "method": "claude mcp add", "status": "updated"})
            self.assertEqual(calls, [
                ["claude", "mcp", "remove", "--scope", "user", "memty"],
                ["claude", "mcp", "add", "--scope", "user", "memty", "--", "/py", "-m", "memty", "mcp"],
            ])
            # Memty itself never rewrote the file Claude Code owns.
            self.assertEqual(paths["Claude Code"].read_bytes(), before)

            calls.clear()
            with patch("memty.connect.subprocess.run", side_effect=fake_run):
                same = connect_clients({"Claude Code": paths["Claude Code"]},
                                       claude_cli="claude", executable="/old")["clients"]
            self.assertEqual(same["Claude Code"]["status"], "already_connected")
            self.assertEqual(calls, [])

    def test_connect_cli_end_to_end(self):
        import os, subprocess, sys
        with tempfile.TemporaryDirectory() as tmp:
            home, paths = self._client_home(tmp)
            paths["Windsurf"].parent.mkdir(parents=True)
            paths["Windsurf"].write_text('{"mcpServers": {"keep": {"command": "x"}}}', encoding="utf-8")
            empty_bin = home / "bin"
            empty_bin.mkdir()  # no `claude` on PATH, so nothing outside tmp is touched
            env = dict(os.environ, HOME=tmp, USERPROFILE=tmp, PATH=str(empty_bin),
                       APPDATA=str(home / "appdata"), LOCALAPPDATA=str(home / "local"),
                       XDG_CONFIG_HOME=str(home / "appdata"))

            def run(*args):
                return subprocess.run([sys.executable, "-m", "memty", "connect", *args], env=env,
                                      capture_output=True, text=True, timeout=15)
            dry = run("--dry-run")
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertEqual(json.loads(dry.stdout)["clients"]["Windsurf"]["status"], "would_add")
            self.assertNotIn("memty", paths["Windsurf"].read_text(encoding="utf-8"))
            done = run()
            self.assertEqual(done.returncode, 0, done.stderr)
            report = json.loads(done.stdout)
            self.assertEqual(report["clients"]["Windsurf"]["status"], "connected")
            self.assertEqual(report["clients"]["Claude Code"]["status"], "not_detected")
            config = json.loads(paths["Windsurf"].read_text(encoding="utf-8"))
            self.assertEqual(set(config["mcpServers"]), {"keep", "memty"})
            self.assertEqual(config["mcpServers"]["memty"]["command"], sys.executable)
            self.assertIn("Restart", report["next_step"])

    def test_real_mcp_stdio_session(self):
        import os, sys
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, MEMTY_DB=str(Path(tmp) / "ledger.sqlite3"))
            async def exercise():
                params = StdioServerParameters(command=sys.executable, args=["-m", "memty", "mcp"], env=env)
                async with stdio_client(params) as (reader, writer):
                    async with ClientSession(reader, writer) as session:
                        await session.initialize()
                        tools = await session.list_tools()
                        self.assertEqual([tool.name for tool in tools.tools], ["memty_sync"])
                        templates = await session.list_resource_templates()
                        self.assertEqual(str(templates.resourceTemplates[0].uriTemplate), "memty://capsule/{namespace}")
                        result = await session.call_tool("memty_sync", {"namespace": "one", "action": "remember", "slot": "color", "value": "blue"})
                        self.assertFalse(result.isError)
                        import subprocess
                        from memty.daemon import status
                        first_pid = status(env["MEMTY_DB"])["pid"]
                        cli = subprocess.run([sys.executable, "-m", "memty", "stats"],
                                             env=env, capture_output=True, text=True, timeout=15)
                        self.assertEqual(cli.returncode, 0, cli.stderr)
                        self.assertEqual(json.loads(cli.stdout)["active_facts"], 1)
                        self.assertEqual(status(env["MEMTY_DB"])["pid"], first_pid)
                        await session.call_tool("memty_sync", {"namespace": "two", "action": "remember", "slot": "color", "value": "red"})
                        resource = await session.read_resource("memty://capsule/one")
                        capsule = json.loads(resource.contents[0].text)
                        self.assertIn("blue", capsule["text"])
                        self.assertNotIn("red", capsule["text"])
                        self.assertLessEqual(estimate_tokens(capsule["text"]), 120)
                        resource = await session.read_resource("memty://capsule/empty")
                        self.assertNotIn("blue", resource.contents[0].text)
            try:
                asyncio.run(exercise())
            finally:
                from memty.daemon import stop
                stop(env["MEMTY_DB"])

if __name__ == "__main__":
    unittest.main()
