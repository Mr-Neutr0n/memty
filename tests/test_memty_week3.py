"""Week 3: localhost web bridge, local fact extraction, and memty clip."""
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from memty.extract import extract_facts, extract_heuristic
from memty.ledger import MemtyLedger
from memty.tokens import estimate_tokens
from memty.web_bridge import (BridgeServer, load_or_create_token, open_pairing, paired_origins,
                               token_path)

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

    def test_headings_paths_and_pasted_capsules_are_not_facts(self):
        # Regression: Gemini answers produced file_1="memty-extension/manifest.json" and
        # note_x="The 2-File Chrome Extension Bridge (Perplexity, ChatGPT, Claude, Gemini)".
        answer = """[Memty context for work.project: facts I saved earlier.]
- Editor: Old value from the capsule
[/Memty]
<memty_state v="1" provider="google"><slots>
work.project.x="also old"
</slots></memty_state>
- The 2-File Chrome Extension Bridge (Perplexity, ChatGPT, Claude, Gemini)
- File 1: memty-extension/manifest.json
- File 2: memty-extension/content.js
- Deploy target: Fly.io
- Done
- The bridge only listens on 127.0.0.1 for safety.
"""
        facts = {f["slot"]: f["value"] for f in extract_heuristic(answer)}
        self.assertEqual(facts, {
            "deploy_target": "Fly.io",
            "bridge_listens_safety": "The bridge only listens on 127.0.0.1 for safety.",
            "files": "memty-extension/manifest.json, memty-extension/content.js",
        })

    def test_code_blocks_are_summarized_not_copied(self):
        answer = """Use this schema:
```python
# memty/db.py
class Ledger:
    def connect(self):
        return sqlite3.connect(self.path)
    def record(self, slot, value):
        pass
```
```sql
CREATE TABLE IF NOT EXISTS atomic_facts (id TEXT);
```
- Storage: SQLite in WAL mode
"""
        facts = {f["slot"]: f["value"] for f in extract_heuristic(answer)}
        self.assertEqual(facts.pop("storage"), "SQLite in WAL mode")
        self.assertEqual(sorted(facts.values()), [
            "Python code in memty/db.py defines connect, record, Ledger",
            "SQL code defines atomic_facts",
        ])
        selected = "function findEditor() {\n  return null;\n}\nconst place = () => {\n  editor = findEditor();\n};"
        self.assertEqual([f["value"] for f in extract_heuristic(selected)],
                         ["JavaScript code defines findEditor, place"])
        self.assertEqual(extract_heuristic("x = 1\ny = 2\nz = x + y"), [])

    def test_prose_fallback_and_caps(self):
        facts = extract_heuristic("Paris is the capital of France. It has about two million residents. Ok.")
        self.assertEqual(len(facts), 2)
        self.assertEqual([f["slot"] for f in facts], ["paris_capital_france", "two_million_residents"])
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
        self.assertCountEqual(body["text"].splitlines(), ["Client: [private]", "Editor: VS Code"])
        self.assertNotIn("MEMTY_REDACTED", body["text"])
        self.assertEqual(body["facts"], 2)
        self.assertEqual(headers["Access-Control-Allow-Origin"], EXT)
        status, body, _ = self.request("GET", "/capsule?namespace=work.project&provider=openai&format=xml")
        self.assertTrue(body["text"].startswith("<memty_state"))
        status, _, _ = self.request("GET", "/capsule?namespace=work.project&format=html")
        self.assertEqual(status, 400)
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

    def test_extension_pairs_itself_once(self):
        status, body, _ = self.request("POST", "/pair", {}, token=False)
        self.assertEqual((status, body["token"]), (200, self.token))
        self.assertEqual(paired_origins(self.ledger.path), [EXT])
        status, body, _ = self.request("POST", "/pair", {}, token=False)  # same extension again
        self.assertEqual(status, 200)
        other = "chrome-extension://zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"
        status, body, _ = self.request("POST", "/pair", {}, token=False, origin=other)
        self.assertEqual((status, body["error"]), (403, "pairing_required"))
        self.assertIn("memty pair", body["message"])
        self.assertNotIn(self.token, json.dumps(body))
        open_pairing(self.ledger.path, 60)  # `memty pair`: the next browser may join
        status, body, _ = self.request("POST", "/pair", {}, token=False, origin=other)
        self.assertEqual((status, body["token"]), (200, self.token))
        self.assertEqual(paired_origins(self.ledger.path), [EXT, other])
        third = "chrome-extension://yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"
        status, _, _ = self.request("POST", "/pair", {}, token=False, origin=third)
        self.assertEqual(status, 403)  # the window closes after one browser joins
        for origin in ("https://evil.example", None):  # web pages and non-browser callers
            status, body, _ = self.request("POST", "/pair", {}, token=False, origin=origin)
            self.assertEqual(status, 403)
            self.assertNotIn("token", body)
        load_or_create_token(self.ledger.path, rotate=True)  # --new-token forgets the pairing
        self.assertEqual(paired_origins(self.ledger.path), [])

    def test_namespaces_include_counts_for_auto_selection(self):
        status, body, _ = self.request("GET", "/namespaces")
        self.assertEqual(body["counts"], {"personal": 1, "work.project": 2})

    def test_extension_preflight(self):
        status, _, headers = self.request("OPTIONS", "/facts", token=False, headers={
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Private-Network": "true"})
        self.assertEqual(status, 204)
        self.assertEqual(headers["Access-Control-Allow-Origin"], EXT)
        self.assertIn("Authorization", headers["Access-Control-Allow-Headers"])
        self.assertEqual(headers["Access-Control-Allow-Private-Network"], "true")

    def test_newest_facts_fit_even_with_many_older_ones(self):
        # Regression: without a query, ties went A-Z, so a fact saved just now
        # (slot "zz_latest") never fit in the capsule.
        for i in range(40):
            self.ledger.record("work.project", f"older_{i:02d}_fact", f"older fact number {i}")
        time.sleep(0.02)  # timestamps are in milliseconds
        self.ledger.record("work.project", "zz_latest", "saved a minute ago")
        status, body, _ = self.request("GET", "/capsule?namespace=work.project&provider=openai")
        self.assertEqual(status, 200)
        self.assertEqual(body["text"].splitlines()[0], "Zz latest: saved a minute ago")
        self.assertLessEqual(estimate_tokens(body["text"]), 350)
        self.assertGreater(body["facts"], 10)

    def test_capsule_pastes_only_the_latest_save(self):
        # Regression: two separate saves (an algorithm note, then a paper review)
        # were pasted into the chat together, so the assistant mixed both topics.
        status, _, _ = self.request("POST", "/facts", {"namespace": "work.project", "confirmed": True, "facts": [
            {"slot": "space_complexity", "value": "O(1)"},
            {"slot": "time_complexity", "value": "O(n x m)"}]})
        self.assertEqual(status, 200)
        time.sleep(0.02)
        status, _, _ = self.request("POST", "/facts", {"namespace": "work.project", "confirmed": True, "facts": [
            {"slot": "hurt_publication_prospects", "value": "Missing dataset details"},
            {"slot": "make_it_stronger", "value": "Ablations with statistical support"},
            {"slot": "client", "value": "Globex"}]})
        self.assertEqual(status, 200)
        status, body, _ = self.request("GET", "/capsule?namespace=work.project&provider=openai")
        self.assertEqual(status, 200, body)
        self.assertEqual(body["text"].splitlines(), [  # saved order, nothing from the earlier save
            "Hurt publication prospects: Missing dataset details",
            "Make it stronger: Ablations with statistical support",
            "Client: [private]"])                       # still private: it was CONFIDENTIAL
        self.assertEqual((body["facts"], body["redacted"]), (3, 1))
        status, body, _ = self.request("GET", "/capsule?namespace=work.project&provider=openai&scope=all")
        self.assertIn("Space complexity: O(1)", body["text"])  # everything, as before, when asked
        status, body, _ = self.request("GET", "/capsule?namespace=work.project&scope=newest")
        self.assertEqual(status, 400)

    def test_user_can_view_edit_and_delete_facts(self):
        status, body, _ = self.request("GET", "/facts?namespace=work.project")
        self.assertEqual(status, 200)
        by_slot = {f["slot"]: f for f in body["facts"]}
        self.assertEqual(by_slot["editor"]["value"], "VS Code")
        self.assertEqual((by_slot["client"]["value"], by_slot["client"]["private"]), (None, True))
        self.assertNotIn("Acme Corp", json.dumps(body))           # private values never reach the browser
        # Rename + edit
        status, body, _ = self.request("POST", "/facts/update", {
            "namespace": "work.project", "slot": "editor", "new_slot": "main_editor", "value": "Neovim"})
        self.assertEqual((status, body["slot"]), (200, "main_editor"))
        self.assertIsNone(self.ledger.find("work.project", "editor") and
                          not self.ledger.find("work.project", "editor")["tombstone"] or None)
        self.assertEqual(self.ledger.find("work.project", "main_editor")["verification_state"], "USER_CONFIRMED")
        # Make public without ever sending the private value from the browser
        status, body, _ = self.request("POST", "/facts/update", {
            "namespace": "work.project", "slot": "client", "value": None, "private": False})
        self.assertEqual((status, body["private"]), (200, False))
        self.assertEqual(self.ledger.find("work.project", "client")["value"], "Acme Corp")
        # Delete, and extraction cannot bring it back
        status, body, _ = self.request("POST", "/facts/delete", {"namespace": "work.project", "slot": "client"})
        self.assertEqual((status, body["deleted"]), (200, True))
        status, body, _ = self.request("POST", "/facts", {"namespace": "work.project",
                                                          "facts": [{"slot": "client", "value": "Other"}]})
        self.assertEqual(body["skipped"][0]["reason"], "TombstonedSlot")
        status, body, _ = self.request("GET", "/facts?namespace=work.project")
        self.assertEqual(sorted(f["slot"] for f in body["facts"]), ["main_editor"])

    def test_reviewed_saves_replace_older_values_and_keep_privacy(self):
        self.ledger.record("work.project", "client", "Acme Corp", sensitivity="CONFIDENTIAL",
                           verification_state="USER_CONFIRMED")
        status, body, _ = self.request("POST", "/facts", {"namespace": "work.project", "confirmed": True,
                                                          "facts": [{"slot": "editor", "value": "Zed"},
                                                                    {"slot": "client", "value": "Globex"}]})
        self.assertEqual((status, len(body["saved"]), body["skipped"]), (200, 2, []))
        self.assertEqual(self.ledger.find("work.project", "editor")["value"], "Zed")
        self.assertEqual(self.ledger.find("work.project", "client")["sensitivity"], "CONFIDENTIAL")

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
                self.assertIn("Editor: VS Code", out.stdout.splitlines())
                self.assertNotIn("[Memty", out.stdout)
                xml = self.run_cli(db, "clip", "work.project", "--print", "--format", "xml")
                self.assertIn("<memty_state", xml.stdout)
                self.assertNotIn("Acme", out.stdout)  # clipboard is treated as a cloud destination
                empty = self.run_cli(db, "clip", "nothing.here", "--print")
                self.assertNotEqual(empty.returncode, 0)
                self.run_cli(db, "remember", "work.project", "pw", "hunter2", "--sensitivity", "SECRET")
                secret = self.run_cli(db, "clip", "work.project", "--print")
                self.assertEqual(secret.returncode, 2)
                self.assertNotIn("hunter2", secret.stdout)
            finally:
                stop(db)

    def test_autostart_command_runs_the_bridge(self):
        from memty import autostart
        args = autostart.command("~/vault.sqlite3", "local", 8765)
        self.assertEqual(args[1:3], ["-m", "memty"])
        self.assertEqual(args[-4:], ["local", "serve", "--port", "8765"])
        self.assertTrue(Path(args[4]).is_absolute())

    def test_extension_installs_from_the_package_and_never_clobbers_other_folders(self):
        from memty import extension
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ext"
            result = extension.install(target)
            manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(result["version"], manifest["version"])
            for name in ["background.js", "content.js", "options.html", "options.js", "icons/icon128.png"]:
                self.assertTrue((target / name).exists(), name)
            (target / "stale.js").write_text("old", encoding="utf-8")
            extension.install(target)  # upgrade replaces the folder cleanly
            self.assertFalse((target / "stale.js").exists())
            other = Path(tmp) / "mine"
            other.mkdir()
            (other / "notes.txt").write_text("keep", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                extension.install(other)
            self.assertEqual((other / "notes.txt").read_text(encoding="utf-8"), "keep")

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
