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

    def test_connect_preserves_existing_config_and_rejects_bad_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            good, bad = Path(tmp) / "good.json", Path(tmp) / "bad.json"
            good.write_text(json.dumps({"theme": "dark", "mcpServers": {"other": {"command": "x"}}}))
            bad.write_text("{bad json")
            result = connect_clients({"Claude Code": good, "Cursor": bad})
            self.assertEqual(result["Claude Code"]["status"], "connected")
            data = json.loads(good.read_text())
            self.assertEqual(data["theme"], "dark")
            self.assertIn("other", data["mcpServers"])
            self.assertEqual(data["mcpServers"]["memty"]["args"], ["-m", "memty", "mcp"])
            self.assertEqual(result["Cursor"]["status"], "error")
            self.assertEqual(bad.read_text(), "{bad json")

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
