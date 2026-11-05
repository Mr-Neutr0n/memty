"""Week 3: localhost web bridge, local fact extraction, and memty clip."""
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from memty.extract import extract_facts, extract_heuristic
from memty.ledger import MemtyLedger
from memty.tokens import estimate_tokens
from memty.web_bridge import BridgeServer, load_or_create_token, token_path

EXT = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"


class ExtractTests(unittest.TestCase):
    def test_bullets_and_key_values_become_valid_slots(self):
        answer = """Here is the plan:

- **Database**: PostgreSQL 16 on [Neon](https://neon.tech) [1]
- Deploy target: Fly.io
* The API uses FastAPI and runs on port 8000.
1. Deadline: March 3
- Database: SQLite for tests
- What should we do next?
- Deploy target: Fly.io
"""
        facts = extract_heuristic(answer)
        by_slot = {f["slot"]: f["value"] for f in facts}
        self.assertEqual(by_slot["database"], "PostgreSQL 16 on Neon")
        self.assertEqual(by_slot["database_2"], "SQLite for tests")
        self.assertEqual(by_slot["deploy_target"], "Fly.io")
        self.assertEqual(by_slot["deadline"], "March 3")
        self.assertIn("The API uses FastAPI and runs on port 8000.", by_slot.values())
        self.assertFalse(any(v.endswith("?") for v in by_slot.values()))
        self.assertEqual(len(facts), 5)  # duplicate "Deploy target" dropped
        with tempfile.TemporaryDirectory() as tmp, MemtyLedger(Path(tmp) / "v.sqlite3") as ledger:
            for fact in facts:  # every proposed slot/value is accepted by the ledger
                ledger.record("work.project", fact["slot"], fact["value"])

    def test_code_from_answers_is_not_saved_as_facts(self):
        # Regression: Gemini answers produced conn="sqlite3.connect(...)" and namespace="str".
        answer = """Here is how to fix it:
def open(self, namespace: str):
    conn = sqlite3.connect(self.dbpath, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn
namespace: str
items: list[str] | None = None
db_path: os.path.join(home, ".memty")
const port = 8765;
// comment: not a fact
```python
x: int
```
- Timeout: 5 seconds avoids lock errors
- Database: PostgreSQL 16 (Neon)
- Use connect() with a timeout
"""
        facts = {f["slot"]: f["value"] for f in extract_heuristic(answer)}
        self.assertEqual(facts.pop("timeout"), "5 seconds avoids lock errors")
        self.assertEqual(facts.pop("database"), "PostgreSQL 16 (Neon)")
        self.assertEqual(list(facts.values()), ["Use connect() with a timeout"])

    def test_prose_fallback_and_caps(self):
        facts = extract_heuristic("Paris is the capital of France. It has about two million residents. Ok.")
        self.assertEqual(len(facts), 2)
        self.assertTrue(all(f["slot"].startswith("note_") for f in facts))
        long = "- " + " ".join(["word"] * 200)
        self.assertLessEqual(estimate_tokens(extract_heuristic(long)[0]["value"]), 40)
        many = "\n".join(f"- fact number {i}" for i in range(40))
        self.assertEqual(len(extract_heuristic(many)), 12)

    def test_ollama_is_used_when_configured_and_falls_back(self):
        class Reply:
            def __init__(self, data): self.data = data
            def read(self): return self.data
            def __enter__(self): return self
            def __exit__(self, *exc): return False
        payload = json.dumps({"response": json.dumps({"facts": [
            {"slot": "Main Language", "value": "Python"}, {"slot": "x", "value": ""}]})}).encode()
        with patch.dict(os.environ, {"MEMTY_OLLAMA_MODEL": "llama3"}), \
             patch("memty.extract.urlrequest.urlopen", return_value=Reply(payload)) as call:
            result = extract_facts("We write everything in Python.")
        self.assertEqual(result, {"facts": [{"slot": "main_language", "value": "Python"}], "method": "ollama"})
        self.assertTrue(call.call_args[0][0].full_url.startswith("http://127.0.0.1:11434/"))
        with patch.dict(os.environ, {"MEMTY_OLLAMA_MODEL": "llama3"}), \
             patch("memty.extract.urlrequest.urlopen", side_effect=OSError("refused")):
            self.assertEqual(extract_facts("- Editor: VS Code")["method"], "heuristic")


class PerCallLedger:
    """Like DaemonLedger in production: no SQLite handle outlives a request thread."""
    def __init__(self, path):
        self.path = path

    def __getattr__(self, name):
        def call(*args, **kwargs):
            with MemtyLedger(self.path) as ledger:
                return getattr(ledger, name)(*args, **kwargs)
        return call


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db = Path(self.tmp.name) / "ledger.sqlite3"
        self.ledger = MemtyLedger(db)
        self.token = load_or_create_token(db)
        self.server = BridgeServer(PerCallLedger(db), self.token, port=0)
        self.port = self.server.port
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.ledger.record("work.project", "editor", "VS Code", verification_state="USER_CONFIRMED")
        self.ledger.record("work.project", "client", "Acme Corp", sensitivity="CONFIDENTIAL")
        self.ledger.record("personal", "color", "green")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.ledger.close()
        self.tmp.cleanup()

    def request(self, method, path, body=None, *, token=True, origin=EXT, host=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": host or f"127.0.0.1:{self.port}"}
        if token:
            h["Authorization"] = "Bearer " + (self.token if token is True else token)
        if origin:
            h["Origin"] = origin
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        h.update(headers or {})
        conn.request(method, path, body=data, headers=h)
        response = conn.getresponse()
        raw = response.read()
        conn.close()
        return response.status, (json.loads(raw) if raw else None), dict(response.getheaders())

    def test_binds_loopback_only_and_token_file_is_private(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        path = token_path(self.ledger.path)
        self.assertEqual(load_or_create_token(self.ledger.path), self.token)
        if os.name != "nt":
            self.assertEqual(path.stat().st_mode & 0o077, 0)
        self.assertNotEqual(load_or_create_token(self.ledger.path, rotate=True), self.token)

    def test_capsule_is_namespace_scoped_redacted_and_within_200_tokens(self):
        status, body, headers = self.request("GET", "/capsule?namespace=work.project&provider=openai")
        self.assertEqual(status, 200, body)
        self.assertIn("VS Code", body["text"])
        self.assertNotIn("green", body["text"])        # other namespace
        self.assertNotIn("Acme Corp", body["text"])    # CONFIDENTIAL for a cloud provider
        self.assertEqual(body["redacted"], 1)
        self.assertNotIn("redactions", body)           # real values never reach the browser
        self.assertNotIn("Acme Corp", json.dumps(body))
        self.assertLessEqual(estimate_tokens(body["text"]), 200)
        self.assertEqual(headers["Access-Control-Allow-Origin"], EXT)
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_secret_facts_are_refused(self):
        self.ledger.record("work.project", "api_key", "sk-123", sensitivity="SECRET")
        status, body, _ = self.request("GET", "/capsule?namespace=work.project&provider=perplexity")
        self.assertEqual(status, 409)
        self.assertEqual(body["error"], "local_routing_required")
        self.assertNotIn("sk-123", json.dumps(body))

    def test_web_pages_and_rebinding_are_blocked(self):
        for origin in ("https://evil.example", "null", "http://127.0.0.1:9999"):
            status, body, headers = self.request("GET", "/capsule?namespace=work.project", origin=origin)
            self.assertEqual((status, body["error"]), (403, "origin_not_allowed"))
            self.assertNotIn("Access-Control-Allow-Origin", headers)
            status, _, headers = self.request("OPTIONS", "/facts", origin=origin, token=False)
            self.assertEqual(status, 403)
            self.assertNotIn("Access-Control-Allow-Origin", headers)
        status, body, _ = self.request("GET", "/capsule?namespace=work.project", host="evil.example:8765")
        self.assertEqual((status, body["error"]), (403, "bad_host"))
        status, body, _ = self.request("GET", "/health", origin="https://evil.example", token=False)
        self.assertEqual(status, 403)

    def test_token_is_required(self):
        for token in (False, "wrong"):
            status, body, _ = self.request("GET", "/capsule?namespace=work.project", token=token)
            self.assertEqual((status, body["error"]), (401, "unauthorized"))
            status, _, _ = self.request("POST", "/facts", {"namespace": "x", "facts": [{}]}, token=token)
            self.assertEqual(status, 401)
        status, body, _ = self.request("GET", "/health", token=False)
        self.assertEqual((status, body), (200, {"ok": True, "service": "memty"}))

    def test_extension_preflight(self):
        status, _, headers = self.request("OPTIONS", "/facts", token=False, headers={
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Private-Network": "true"})
        self.assertEqual(status, 204)
        self.assertEqual(headers["Access-Control-Allow-Origin"], EXT)
        self.assertIn("Authorization", headers["Access-Control-Allow-Headers"])
        self.assertEqual(headers["Access-Control-Allow-Private-Network"], "true")

    def test_extract_then_save_never_overwrites_confirmed_facts(self):
        status, body, _ = self.request("POST", "/extract", {"text": "- Editor: Vim\n- Framework: Next.js"})
        self.assertEqual(status, 200, body)
        self.assertEqual(body["method"], "heuristic")
        self.assertEqual(self.ledger.stats()["active_facts"], 3)  # extract alone writes nothing
        status, body, _ = self.request("POST", "/facts", {"namespace": "work.project", "facts": body["facts"]})
        self.assertEqual(status, 200, body)
        self.assertEqual([s["slot"] for s in body["saved"]], ["framework"])
        self.assertEqual(body["skipped"][0]["slot"], "editor")      # USER_CONFIRMED stays
        self.assertEqual(self.ledger.find("work.project", "editor")["value"], "VS Code")
        saved = self.ledger.find("work.project", "framework")
        self.assertEqual((saved["value"], saved["verification_state"]), ("Next.js", "EXTRACTED"))

    def test_rejects_bad_requests(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("POST", "/facts", body=b'{"namespace":"x"}', headers={
            "Host": f"127.0.0.1:{self.port}", "Authorization": "Bearer " + self.token,
            "Content-Type": "text/plain"})  # what a CSRF form/no-cors fetch would send
        self.assertEqual(conn.getresponse().status, 415)
        conn.close()
        status, _, _ = self.request("POST", "/extract", {"text": "x" * 300_000})
        self.assertEqual(status, 413)
        status, _, _ = self.request("POST", "/facts", {"namespace": "Bad Name!", "facts": [{"slot": "a", "value": "b"}]})
        self.assertEqual(status, 200)  # per-fact validation reported, not a crash
        status, body, _ = self.request("GET", "/capsule")
        self.assertEqual((status, body["error"]), (400, "invalid_request"))
        status, body, _ = self.request("GET", "/namespaces")
        self.assertEqual(body["namespaces"], ["personal", "work.project"])


class ClipTests(unittest.TestCase):
    def run_cli(self, db, *args):
        env = dict(os.environ, MEMTY_DB=str(db))
        return subprocess.run([sys.executable, "-m", "memty", *args], env=env,
                              capture_output=True, text=True, encoding="utf-8", timeout=30)

    def test_clip_print_and_privacy(self):
        from memty.daemon import stop
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "ledger.sqlite3"
            try:
                self.assertEqual(self.run_cli(db, "remember", "work.project", "editor", "VS Code").returncode, 0)
                self.run_cli(db, "remember", "work.project", "client", "Acme", "--sensitivity", "CONFIDENTIAL")
                out = self.run_cli(db, "clip", "work.project", "--print")
                self.assertEqual(out.returncode, 0, out.stderr)
                self.assertIn("<memty_state", out.stdout)
                self.assertIn("VS Code", out.stdout)
                self.assertNotIn("Acme", out.stdout)  # clipboard is treated as a cloud destination
                empty = self.run_cli(db, "clip", "nothing.here", "--print")
                self.assertNotEqual(empty.returncode, 0)
                self.run_cli(db, "remember", "work.project", "pw", "hunter2", "--sensitivity", "SECRET")
                secret = self.run_cli(db, "clip", "work.project", "--print")
                self.assertEqual(secret.returncode, 2)
                self.assertNotIn("hunter2", secret.stdout)
            finally:
                stop(db)

    def test_copy_text_uses_platform_tool(self):
        from memty import clipboard
        with patch("memty.clipboard.subprocess.run") as run:
            clipboard.copy_text("capsule ✓")
        argv, kwargs = run.call_args[0][0], run.call_args[1]
        if sys.platform == "win32":
            self.assertEqual(argv, ["clip"])
            self.assertEqual(kwargs["input"], "capsule ✓".encode("utf-16"))
        self.assertTrue(kwargs["check"])
        with patch("memty.clipboard._command", return_value=None):
            with self.assertRaises(RuntimeError):
                clipboard.copy_text("x")


if __name__ == "__main__":
    unittest.main()
