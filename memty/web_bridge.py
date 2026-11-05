"""Localhost HTTP bridge so browser assistants can use the local Memty vault.

``memty serve --port 8765`` binds strictly to ``127.0.0.1``. A localhost
server is reachable by *every* web page the user opens, so it is locked down:

* **Pairing token**: every data route needs ``Authorization: Bearer <token>``.
  The token lives beside the vault (``<db>.web-token``, owner-only). The
  extension pairs itself through ``POST /pair`` (trust on first use): the first
  browser-extension origin to ask is remembered, and only that origin can fetch
  the token again. ``memty serve --new-token`` rotates the token and forgets it.
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
import threading
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

from .compiler import LocalRoutingRequired, render_plain
from .extract import MAX_INPUT_CHARS, extract_facts
from .ledger import LockedSlot, TombstonedSlot
from .tokens import estimate_tokens

DEFAULT_PORT = 8765
WEB_CAPSULE_TOKENS = 350
# Compile with headroom, then trim the readable text to the real budget, so the
# compiler's XML section caps never hide facts that would fit as plain lines.
TEXT_COMPILE_BUDGET = 1500
PRIVATE = {"CONFIDENTIAL", "SECRET"}
MAX_BODY = 256 * 1024
MAX_SAVE = 25
EXTENSION_SCHEMES = ("chrome-extension://", "moz-extension://", "safari-web-extension://")
SAVE_BATCH_PREFIX = "save_"
# Saves made before batch ids existed: facts written this close to the newest one
# count as the same save.
LEGACY_BATCH_WINDOW_MS = 5_000


def latest_batch(facts: list[dict]) -> list[dict]:
    """The facts from the most recent save.

    One Save click comes back in the order it was saved; facts without a batch id
    (older saves, CLI writes) come back newest first, so trimming drops the oldest.
    """
    if not facts:
        return []
    when = lambda f: int(f["updated_at"] or 0)  # noqa: E731
    newest = max(facts, key=when)
    source = str(newest.get("source_id") or "")
    if source.startswith(SAVE_BATCH_PREFIX):
        return sorted((f for f in facts if f.get("source_id") == source), key=when)
    cutoff = when(newest) - LEGACY_BATCH_WINDOW_MS
    return sorted((f for f in facts if when(f) >= cutoff
                   and not str(f.get("source_id") or "").startswith(SAVE_BATCH_PREFIX)),
                  key=when, reverse=True)


def token_path(db: str | Path) -> Path:
    db = Path(db).expanduser()
    return db.with_name(db.name + ".web-token")


def state_path(db: str | Path) -> Path:
    db = Path(db).expanduser()
    return db.with_name(db.name + ".web-bridge.json")


def paired_path(db: str | Path) -> Path:
    db = Path(db).expanduser()
    return db.with_name(db.name + ".web-paired.json")


PAIR_WINDOW_SECONDS = 120
MAX_PAIRED = 5


def _read_paired(db: str | Path) -> dict:
    try:
        value = json.loads(paired_path(db).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def paired_origins(db: str | Path) -> list[str]:
    return [str(item) for item in _read_paired(db).get("origins", [])]


def pairing_open(db: str | Path) -> bool:
    return float(_read_paired(db).get("open_until", 0)) > time.time()


def _write_paired(db: str | Path, origins: list[str], open_until: float = 0) -> None:
    path = paired_path(db)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".{os.getpid()}.tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump({"origins": origins, "open_until": open_until}, stream)
    os.replace(temp, path)


def open_pairing(db: str | Path, seconds: int = PAIR_WINDOW_SECONDS) -> float:
    """Let one more browser extension pair during the next ``seconds`` (``memty pair``).

    Needs a local terminal, so a web page or another extension can't open it.
    The running bridge reads this file on every pairing request: no restart needed.
    """
    until = time.time() + seconds
    _write_paired(db, paired_origins(db), until)
    return until


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
    if rotate:  # a new token also forgets which extension was paired
        try:
            paired_path(db).unlink()
        except OSError:
            pass
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
                 allowed_origins: list[str] | None = None, quiet: bool = True,
                 db: str | Path | None = None):
        self.ledger = ledger
        self.token = token
        self.db = db or getattr(ledger, "path", None)
        self.pair_lock = threading.Lock()
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
            # Drain (bounded) so Windows does not reset the socket before the 413 arrives.
            remaining = min(max(length, 0), 16 * MAX_BODY)
            while remaining > 0 and (chunk := self.rfile.read(min(remaining, 65536))):
                remaining -= len(chunk)
            self.close_connection = True
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
            elif url.path == "/facts":
                self._list_facts(query)
            elif url.path == "/namespaces":
                counts: dict[str, int] = {}
                for fact in self.server.ledger.list():
                    counts[fact["namespace"]] = counts.get(fact["namespace"], 0) + 1
                self._send(HTTPStatus.OK, {"namespaces": sorted(counts), "counts": counts})
            else:
                self._error(HTTPStatus.NOT_FOUND, "not_found", "Unknown route.")
        except ValueError as error:
            self._error(HTTPStatus.BAD_REQUEST, "invalid_request", str(error))

    def do_POST(self):
        url = urlsplit(self.path)
        if url.path == "/pair":
            if self._guard(auth=False):
                self._pair()
            return
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
            elif url.path == "/facts/update":
                self._update(body)
            elif url.path == "/facts/delete":
                self._delete(body)
            else:
                self._error(HTTPStatus.NOT_FOUND, "not_found", "Unknown route.")
        except ValueError as error:
            self._error(HTTPStatus.BAD_REQUEST, "invalid_request", str(error))

    # -- routes ---------------------------------------------------------
    def _pair(self) -> None:
        """Hand the token to the browser extension without copy-pasting (trust on first use)."""
        origin = (self.headers.get("Origin") or "").rstrip("/")
        if not origin.startswith(EXTENSION_SCHEMES):
            self._error(HTTPStatus.FORBIDDEN, "origin_not_allowed", "Only a browser extension can pair.")
            return
        if self.server.db is None:
            self._error(HTTPStatus.CONFLICT, "pairing_unavailable",
                        "Pair manually: paste `memty serve --show-token` into the extension options.")
            return
        with self.server.pair_lock:
            origins = paired_origins(self.server.db)
            if origins and origin not in origins:
                if not pairing_open(self.server.db):
                    self._error(HTTPStatus.FORBIDDEN, "pairing_required",
                                "This browser isn't connected to Memty yet. In a terminal, run: "
                                "memty pair. Then click Try again.")
                    return
                # The user opened a pairing window: add this browser, then close the window.
                _write_paired(self.server.db, (origins + [origin])[-MAX_PAIRED:])
            elif not origins:
                _write_paired(self.server.db, [origin])
        self._send(HTTPStatus.OK, {"token": self.server.token, "port": self.server.port})

    def _capsule(self, query: dict) -> None:
        namespace = query.get("namespace", "").strip()
        if not namespace:
            raise ValueError("namespace is required")
        tokens = int(query.get("tokens", WEB_CAPSULE_TOKENS))
        if not 1 <= tokens <= 600:
            raise ValueError("tokens must be between 1 and 600")
        provider = query.get("provider", "web").strip() or "web"
        style = query.get("format", "text")
        if style not in {"text", "xml"}:
            raise ValueError("format must be text or xml")
        question = query.get("query", "").strip()
        # With no question to rank by, hand over only the most recent save: mixing
        # every earlier save into one paste confuses the chat assistant.
        scope = query.get("scope", "latest" if style == "text" and not question else "all")
        if scope not in {"latest", "all"}:
            raise ValueError("scope must be latest or all")
        if scope == "latest" and style != "text":
            raise ValueError("scope=latest needs format=text")
        try:
            result = self.server.ledger.context(
                question, provider=provider, namespace=namespace,
                token_budget=TEXT_COMPILE_BUDGET if style == "text" else tokens, strict_namespace=True)
        except LocalRoutingRequired as error:
            self._error(HTTPStatus.CONFLICT, "local_routing_required",
                        "A SECRET fact matched; it cannot be sent to a web assistant.",
                        namespace=error.namespace, slot=error.slot)
            return
        if scope == "latest" and result["text"]:
            # Keep the compiler's privacy decisions (redacted values, refused facts),
            # just narrowed to the latest save and shown in the order it was saved.
            order = {f["id"]: i for i, f in enumerate(latest_batch(
                self.server.ledger.list(namespace=namespace)))}
            kept = sorted((c for c in result["citations"] if c.get("id") in order),
                          key=lambda c: order[c["id"]])
            result = {**result, "citations": kept, "text": result["text"] if kept else ""}
        # Chat assistants read plain "Title: value" lines far better than XML slots.
        text = (render_plain(result, namespace, tokens) if style == "text" and result["text"]
                else result["text"])
        lines = [line for line in text.splitlines() if not line.startswith("Summary:")]
        # Redaction maps hold the real CONFIDENTIAL values: never send them to a browser.
        self._send(HTTPStatus.OK, {"text": text, "approx_tokens": estimate_tokens(text),
                                   "namespace": namespace, "provider": provider,
                                   "facts": len(lines) if style == "text" else result.get("injected_count", 0),
                                   "redacted": (text.count("[private]") if style == "text" else
                                                len(result.get("redactions") or {}))})

    # -- user-controlled fact management (view, edit, delete) -----------
    @staticmethod
    def _namespace(value) -> str:
        namespace = str(value or "").strip()
        if not namespace:
            raise ValueError("namespace is required")
        return namespace

    def _list_facts(self, query: dict) -> None:
        namespace = self._namespace(query.get("namespace"))
        facts = []
        for fact in self.server.ledger.list(namespace=namespace):
            private = fact["sensitivity"] in PRIVATE
            facts.append({
                "slot": fact["slot"],
                # Private values never reach the browser; they can still be replaced or deleted.
                "value": None if private else fact["value"],
                "private": private, "sensitivity": fact["sensitivity"],
                "source": "you" if fact["verification_state"] != "EXTRACTED" else "saved from chat",
                "updated_at": fact["updated_at"],
            })
        facts.sort(key=lambda item: -int(item["updated_at"] or 0))
        self._send(HTTPStatus.OK, {"namespace": namespace, "facts": facts})

    def _update(self, body: dict) -> None:
        """A user edit: written as USER_CONFIRMED, so chat extraction never overwrites it."""
        namespace = self._namespace(body.get("namespace"))
        slot = str(body.get("slot", "")).strip()
        new_slot = str(body.get("new_slot") or slot).strip()
        value = body.get("value")
        current = next((f for f in self.server.ledger.list(namespace=namespace) if f["slot"] == slot), None)
        if value is None or not str(value).strip():
            if current is None:
                raise ValueError("value is required")
            value = current["value"]  # rename or privacy change: keep the stored value server-side
        if "private" in body:
            sensitivity = "CONFIDENTIAL" if body["private"] else "PUBLIC"
        else:
            sensitivity = current["sensitivity"] if current else "PUBLIC"
        record = self.server.ledger.record(namespace, new_slot, str(value), confidence=1.0,
                                           verification_state="USER_CONFIRMED", sensitivity=sensitivity)
        if current is not None and record["slot"] != slot:
            self.server.ledger.forget(namespace, slot)  # renamed: remove the old title
        self._send(HTTPStatus.OK, {"namespace": namespace, "slot": record["slot"],
                                   "version": record.get("version"),
                                   "private": record["sensitivity"] in PRIVATE})

    def _delete(self, body: dict) -> None:
        namespace = self._namespace(body.get("namespace"))
        slot = str(body.get("slot", "")).strip()
        if not slot:
            raise ValueError("slot is required")
        # forget() tombstones the slot and purges its history; chat extraction can't bring it back.
        result = self.server.ledger.forget(namespace, slot)
        self._send(HTTPStatus.OK, {"namespace": namespace, "slot": slot, "deleted": result is not None})

    def _save(self, body: dict) -> None:
        namespace = str(body.get("namespace", "")).strip()
        facts = body.get("facts")
        if not namespace or not isinstance(facts, list) or not 1 <= len(facts) <= MAX_SAVE:
            raise ValueError(f"namespace and 1-{MAX_SAVE} facts are required")
        # confirmed: the user reviewed (and possibly edited) each fact and clicked Save,
        # so it is their own statement and replaces an older value for the same title.
        # Without it, facts stay EXTRACTED: they never overwrite user-confirmed slots
        # and never resurrect slots the user forgot.
        confirmed = body.get("confirmed") is True
        existing = ({f["slot"]: f["sensitivity"] for f in self.server.ledger.list(namespace=namespace)}
                    if confirmed else {})
        # Every fact from one Save click shares a batch id, so the capsule can hand
        # the chat just the latest save instead of mixing it with older ones.
        batch = SAVE_BATCH_PREFIX + secrets.token_hex(8)
        saved, skipped = [], []
        for item in facts:
            slot = str(item.get("slot", "")) if isinstance(item, dict) else ""
            value = str(item.get("value", "")) if isinstance(item, dict) else ""
            try:
                if confirmed:  # keep a private fact private when its value is updated
                    record = self.server.ledger.record(
                        namespace, slot, value, confidence=1.0, verification_state="USER_CONFIRMED",
                        sensitivity=existing.get(slot.strip().casefold(), "PUBLIC"), source_id=batch)
                else:
                    record = self.server.ledger.record(namespace, slot, value, confidence=0.7,
                                                       verification_state="EXTRACTED", source_id=batch)
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
    with BridgeServer(ledger, token, port=port, allowed_origins=allowed_origins, quiet=quiet,
                      db=db) as server:
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
