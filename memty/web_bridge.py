"""Localhost HTTP bridge so browser assistants can use the local Memty vault.

``memty serve --port 8765`` binds strictly to ``127.0.0.1``. A localhost
server is reachable by *every* web page the user opens, so it is locked down:

* **Pairing token**: every data route needs ``Authorization: Bearer <token>``.
  The token lives beside the vault (``<db>.web-token``, owner-only) and is
  pasted once into the extension's options page.
* **Origin allow-list**: requests from web pages (``https://...``) are refused;
  only browser-extension origins (or an explicit ``--allow-origin``) are accepted.
* **Host check**: the ``Host`` header must be ``127.0.0.1``/``localhost`` on our
  port, which defeats DNS-rebinding attacks.
* **JSON only**: writes need ``Content-Type: application/json``, which a page
  cannot send cross-origin without a (refused) preflight.

Capsules are compiled for the calling assistant as a *cloud* provider, so the
ledger's sensitivity rules apply: CONFIDENTIAL values are redacted, SECRET facts
are refused, and redaction maps are never sent to the browser.
"""
from __future__ import annotations

import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time
from urllib import request as urlrequest
from urllib.parse import parse_qs, urlsplit

from .compiler import LocalRoutingRequired
from .extract import MAX_INPUT_CHARS, extract_facts
from .ledger import LockedSlot, TombstonedSlot

DEFAULT_PORT = 8765
WEB_CAPSULE_TOKENS = 200
MAX_BODY = 256 * 1024
MAX_SAVE = 25
EXTENSION_SCHEMES = ("chrome-extension://", "moz-extension://", "safari-web-extension://")


def token_path(db: str | Path) -> Path:
    db = Path(db).expanduser()
    return db.with_name(db.name + ".web-token")


def state_path(db: str | Path) -> Path:
    db = Path(db).expanduser()
    return db.with_name(db.name + ".web-bridge.json")


def load_or_create_token(db: str | Path, *, rotate: bool = False) -> str:
    """Return the pairing token, creating an owner-only token file if needed."""
    path = token_path(db)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rotate:
        try:
            token = path.read_text(encoding="utf-8").strip()
            if len(token) >= 32:
                return token
        except OSError:
            pass
    token = secrets.token_urlsafe(32)
    temp = path.with_name(path.name + f".{os.getpid()}.tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(token + "\n")
    os.replace(temp, path)
    return token


class BridgeServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, ledger, token: str, *, port: int = DEFAULT_PORT,
                 allowed_origins: list[str] | None = None, quiet: bool = True):
        self.ledger = ledger
        self.token = token
        self.allowed_origins = {o.rstrip("/") for o in (allowed_origins or [])}
        self.quiet = quiet
        # Never configurable: the bridge must not be reachable from the network.
        super().__init__(("127.0.0.1", port), BridgeHandler)

    @property
    def port(self) -> int:
        return self.server_address[1]

    def origin_allowed(self, origin: str | None) -> bool:
        if origin is None:
            return True  # Not a browser cross-origin request (CLI, curl); token still required.
        origin = origin.rstrip("/")
        if self.allowed_origins:
            return origin in self.allowed_origins
        return origin.startswith(EXTENSION_SCHEMES)


class BridgeHandler(BaseHTTPRequestHandler):
    server: BridgeServer
    server_version = "memty-bridge"
    sys_version = ""

    # -- plumbing -----------------------------------------------------
    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        if not self.server.quiet:  # Never logs bodies, tokens, or query strings.
            sys.stderr.write("%s %s\n" % (self.command, urlsplit(self.path).path))

    def _send(self, status: int, body: dict, origin_ok: bool = True) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Vary", "Origin")
        origin = self.headers.get("Origin")
        if origin and origin_ok:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status: int, error: str, message: str, **extra) -> None:
        self._send(status, {"error": error, "message": message, **extra})

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        return host in {f"127.0.0.1:{self.server.port}", f"localhost:{self.server.port}"}

    def _guard(self, *, auth: bool = True) -> bool:
        if not self._host_ok():
            self._send(HTTPStatus.FORBIDDEN, {"error": "bad_host",
                       "message": "Use http://127.0.0.1:%d" % self.server.port}, origin_ok=False)
            return False
        if not self.server.origin_allowed(self.headers.get("Origin")):
            self._send(HTTPStatus.FORBIDDEN, {"error": "origin_not_allowed",
                       "message": "Only the Memty browser extension may call this bridge."}, origin_ok=False)
            return False
        if auth:
            supplied = self.headers.get("Authorization", "")
            expected = "Bearer " + self.server.token
            if not hmac.compare_digest(supplied.encode(), expected.encode()):
                self._error(HTTPStatus.UNAUTHORIZED, "unauthorized",
                            "Missing or wrong pairing token. Run: memty serve --show-token")
                return False
        return True

    def _json_body(self) -> dict | None:
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "json_required", "Send application/json.")
            return None
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "too_large", "Request body is too large.")
            return None
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            body = None
        if not isinstance(body, dict):
            self._error(HTTPStatus.BAD_REQUEST, "bad_json", "Body must be a JSON object.")
            return None
        return body

    # -- verbs ----------------------------------------------------------
    def do_OPTIONS(self):  # CORS preflight
        origin = self.headers.get("Origin")
        if not self._host_ok() or origin is None or not self.server.origin_allowed(origin):
            self._send(HTTPStatus.FORBIDDEN, {"error": "origin_not_allowed"}, origin_ok=False)
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Vary", "Origin")
        if self.headers.get("Access-Control-Request-Private-Network"):
            self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        url = urlsplit(self.path)
        query = {k: v[-1] for k, v in parse_qs(url.query).items()}
        if url.path == "/health":
            if self._guard(auth=False):
                self._send(HTTPStatus.OK, {"ok": True, "service": "memty"})
            return
        if not self._guard():
            return
        try:
            if url.path == "/capsule":
                self._capsule(query)
            elif url.path == "/namespaces":
                facts = self.server.ledger.list()
                self._send(HTTPStatus.OK, {"namespaces": sorted({f["namespace"] for f in facts})})
            else:
                self._error(HTTPStatus.NOT_FOUND, "not_found", "Unknown route.")
        except ValueError as error:
            self._error(HTTPStatus.BAD_REQUEST, "invalid_request", str(error))

    def do_POST(self):
        url = urlsplit(self.path)
        if not self._guard():
            return
        body = self._json_body()
        if body is None:
            return
        try:
            if url.path == "/extract":
                text = str(body.get("text", ""))
                if not text.strip() or len(text) > MAX_INPUT_CHARS:
                    raise ValueError(f"text must be 1-{MAX_INPUT_CHARS} characters")
                self._send(HTTPStatus.OK, extract_facts(text))
            elif url.path == "/facts":
                self._save(body)
            else:
                self._error(HTTPStatus.NOT_FOUND, "not_found", "Unknown route.")
        except ValueError as error:
            self._error(HTTPStatus.BAD_REQUEST, "invalid_request", str(error))

    # -- routes ---------------------------------------------------------
    def _capsule(self, query: dict) -> None:
        namespace = query.get("namespace", "").strip()
        if not namespace:
            raise ValueError("namespace is required")
        tokens = int(query.get("tokens", WEB_CAPSULE_TOKENS))
        if not 1 <= tokens <= 600:
            raise ValueError("tokens must be between 1 and 600")
        provider = query.get("provider", "web").strip() or "web"
        try:
            result = self.server.ledger.context(query.get("query", ""), provider=provider,
                                                namespace=namespace, token_budget=tokens,
                                                strict_namespace=True)
        except LocalRoutingRequired as error:
            self._error(HTTPStatus.CONFLICT, "local_routing_required",
                        "A SECRET fact matched; it cannot be sent to a web assistant.",
                        namespace=error.namespace, slot=error.slot)
            return
        # Redaction maps hold the real CONFIDENTIAL values: never send them to a browser.
        self._send(HTTPStatus.OK, {"text": result["text"], "approx_tokens": result["approx_tokens"],
                                   "namespace": namespace, "provider": provider,
                                   "redacted": len(result.get("redactions") or {})})

    def _save(self, body: dict) -> None:
        namespace = str(body.get("namespace", "")).strip()
        facts = body.get("facts")
        if not namespace or not isinstance(facts, list) or not 1 <= len(facts) <= MAX_SAVE:
            raise ValueError(f"namespace and 1-{MAX_SAVE} facts are required")
        saved, skipped = [], []
        for item in facts:
            slot = str(item.get("slot", "")) if isinstance(item, dict) else ""
            value = str(item.get("value", "")) if isinstance(item, dict) else ""
            try:
                # EXTRACTED: AI-derived facts never overwrite user-confirmed slots
                # and never resurrect slots the user forgot.
                record = self.server.ledger.record(namespace, slot, value, confidence=0.7,
                                                   verification_state="EXTRACTED")
                saved.append({"slot": record["slot"], "version": record.get("version")})
            except (LockedSlot, TombstonedSlot) as error:
                skipped.append({"slot": slot, "reason": type(error).__name__, "message": str(error)})
            except ValueError as error:
                skipped.append({"slot": slot, "reason": "invalid", "message": str(error)})
        self._send(HTTPStatus.OK, {"namespace": namespace, "saved": saved, "skipped": skipped})


# ---------------------------------------------------------------------------
def health(port: int, timeout: float = 1.0) -> bool:
    try:
        with urlrequest.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as response:
            return json.loads(response.read()).get("service") == "memty"
    except (OSError, ValueError):
        return False


def serve(db, user_id, *, port: int = DEFAULT_PORT, allowed_origins=None, quiet=True) -> None:
    from .daemon import DaemonLedger
    token = load_or_create_token(db)
    ledger = DaemonLedger(db, user_id)  # Shares the one memtyd process with MCP and CLI.
    with BridgeServer(ledger, token, port=port, allowed_origins=allowed_origins, quiet=quiet) as server:
        state_path(db).write_text(json.dumps({"pid": os.getpid(), "port": server.port}), encoding="utf-8")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            try:
                state_path(db).unlink()
            except OSError:
                pass


def start_background(db, user_id, *, port: int = DEFAULT_PORT, allowed_origins=None) -> dict:
    if health(port):
        return {"running": True, "port": port, "already_running": True}
    args = [sys.executable, "-m", "memty", "--db", str(db), "--user", user_id, "serve", "--port", str(port)]
    for origin in allowed_origins or []:
        args += ["--allow-origin", origin]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=flags, start_new_session=(os.name != "nt"), close_fds=True)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if health(port):
            return {"running": True, "port": port}
        time.sleep(0.1)
    raise RuntimeError(f"memty serve did not start on 127.0.0.1:{port}; run it in the foreground to see why")


def stop_background(db) -> dict:
    try:
        state = json.loads(state_path(db).read_text(encoding="utf-8"))
        # A stale state file's pid may now belong to an unrelated process.
        if not health(int(state["port"])):
            return {"stopped": False, "reason": "not_running"}
        os.kill(int(state["pid"]), signal.SIGTERM)
    except (OSError, ValueError, KeyError):
        return {"stopped": False, "reason": "not_running"}
    try:
        state_path(db).unlink()
    except OSError:
        pass
    return {"stopped": True, "pid": state["pid"]}
