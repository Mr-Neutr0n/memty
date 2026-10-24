"""Fast, local-first, event-sourced memory ledger.

The ledger stores immutable fact versions in SQLite. A fact is addressed by a
canonical namespace and slot key; changing a slot appends a new version and
closes the previous version's valid-time interval. No model or network calls
are made by this module.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


SCHEMA_VERSION = 2
_PROVIDERS = re.compile(r"^[a-zA-Z0-9_.-]{1,80}$")
_KEY_PART = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _normalize_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    except (TypeError, ValueError) as error:
        raise ValueError("timestamp must be ISO-8601 and include a timezone") from error


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[\w'-]{2,}", text.casefold(), re.UNICODE))


def _normalize_namespace(namespace: str) -> str:
    parts = [part.strip().lower() for part in str(namespace).split(".")]
    if not parts or any(not _KEY_PART.fullmatch(part) for part in parts):
        raise ValueError("namespace must contain lowercase dot-separated key parts")
    return ".".join(parts)


def _normalize_key(slot_key: str) -> str:
    key = str(slot_key).strip().lower()
    if not _KEY_PART.fullmatch(key):
        raise ValueError("slot_key must be a lowercase key using letters, numbers, '_' or '-'")
    return key


class MemoryLedger:
    """A per-user SQLite memory vault with temporal state and access policies."""

    FORMAT = "nexor-memory-ledger-v1"

    def __init__(self, path: str | Path, user_id: str = "local"):
        if not user_id or len(user_id) > 200:
            raise ValueError("user_id must be a non-empty identifier of at most 200 characters")
        self.path = Path(path)
        self.user_id = str(user_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS ledger_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    memory_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    namespace TEXT NOT NULL,
                    slot_key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    status TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    verification_state TEXT NOT NULL,
                    sensitivity_tier TEXT NOT NULL,
                    allowed_providers_json TEXT NOT NULL,
                    blocked_providers_json TEXT NOT NULL,
                    ephemeral_redaction INTEGER NOT NULL,
                    valid_from TEXT NOT NULL,
                    valid_to TEXT,
                    recorded_at TEXT NOT NULL,
                    source_conversation_id TEXT,
                    source_quote TEXT,
                    source_message_hash TEXT,
                    extracted_by_model TEXT,
                    supersedes_id TEXT,
                    payload_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ledger_user_slot_seq
                    ON ledger_events(user_id, namespace, slot_key, seq DESC);
                CREATE INDEX IF NOT EXISTS ledger_user_status_seq
                    ON ledger_events(user_id, status, seq DESC);
                CREATE TABLE IF NOT EXISTS pending_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    proposal_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                );
                CREATE INDEX IF NOT EXISTS proposals_user_status
                    ON pending_proposals(user_id, status, created_at DESC);
                CREATE TABLE IF NOT EXISTS vault_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(ledger_events)").fetchall()}
            if "source_quote" not in columns:
                db.execute("ALTER TABLE ledger_events ADD COLUMN source_quote TEXT")
            version = db.execute("SELECT value FROM vault_meta WHERE key='schema_version'").fetchone()
            if version is not None and int(version[0]) > SCHEMA_VERSION:
                raise ValueError("This vault was created by a newer SmartMemory version")
            db.execute("INSERT OR REPLACE INTO vault_meta(key,value) VALUES('schema_version',?)", (str(SCHEMA_VERSION),))
            db.execute("INSERT OR REPLACE INTO vault_meta(key,value) VALUES('format',?)", (self.FORMAT,))

    @staticmethod
    def _latest_rows(db: sqlite3.Connection, user_id: str) -> list[sqlite3.Row]:
        return db.execute("""
            SELECT e.* FROM ledger_events e
            JOIN (SELECT memory_id, MAX(seq) AS seq FROM ledger_events WHERE user_id=? GROUP BY memory_id) latest
            ON latest.memory_id=e.memory_id AND latest.seq=e.seq
            WHERE e.user_id=?
        """, (user_id, user_id)).fetchall()

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["memory_id"], "namespace": row["namespace"], "slot_key": row["slot_key"],
            "value": row["value"], "status": row["status"], "confidence": row["confidence"],
            "verification_state": row["verification_state"], "sensitivity_tier": row["sensitivity_tier"],
            "allowed_providers": json.loads(row["allowed_providers_json"]),
            "blocked_providers": json.loads(row["blocked_providers_json"]),
            "ephemeral_redaction": bool(row["ephemeral_redaction"]),
            "valid_from": row["valid_from"], "valid_to": row["valid_to"],
            "recorded_at": row["recorded_at"], "source_conversation_id": row["source_conversation_id"],
            "source_quote": row["source_quote"],
            "source_message_hash": row["source_message_hash"], "extracted_by_model": row["extracted_by_model"],
            "supersedes_id": row["supersedes_id"], "content_hash": row["payload_hash"],
        }

    @staticmethod
    def _append_state(db: sqlite3.Connection, *, memory_id: str, user_id: str, event_type: str,
                      namespace: str, slot_key: str, value: str, status: str, confidence: float,
                      verification_state: str, sensitivity_tier: str, allowed_providers: list[str],
                      blocked_providers: list[str], ephemeral_redaction: bool, valid_from: str,
                      valid_to: str | None, recorded_at: str, source_conversation_id: str | None,
                      source_quote: str | None, source_message_hash: str | None, extracted_by_model: str | None,
                      supersedes_id: str | None) -> None:
        fields = {"memory_id": memory_id, "user_id": user_id, "event_type": event_type,
                  "namespace": namespace, "slot_key": slot_key, "value": value, "status": status,
                  "confidence": confidence, "verification_state": verification_state,
                  "sensitivity_tier": sensitivity_tier, "allowed_providers": allowed_providers,
                  "blocked_providers": blocked_providers, "ephemeral_redaction": ephemeral_redaction,
                  "valid_from": valid_from, "valid_to": valid_to, "recorded_at": recorded_at,
                  "source_conversation_id": source_conversation_id,
                  "source_quote": source_quote,
                  "source_message_hash": source_message_hash, "extracted_by_model": extracted_by_model,
                  "supersedes_id": supersedes_id}
        digest = hashlib.sha256(_canonical(fields)).hexdigest()
        db.execute("""
            INSERT INTO ledger_events(event_id,memory_id,user_id,event_type,namespace,slot_key,value,status,
                confidence,verification_state,sensitivity_tier,allowed_providers_json,blocked_providers_json,
                ephemeral_redaction,valid_from,valid_to,recorded_at,source_conversation_id,source_quote,source_message_hash,
                extracted_by_model,supersedes_id,payload_hash,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (str(uuid.uuid4()), memory_id, user_id, event_type, namespace, slot_key, value, status,
              confidence, verification_state, sensitivity_tier, json.dumps(allowed_providers),
              json.dumps(blocked_providers), int(ephemeral_redaction), valid_from, valid_to, recorded_at,
              source_conversation_id, source_quote, source_message_hash, extracted_by_model, supersedes_id, digest, _utc_now()))

    def record(self, namespace: str, slot_key: str, value: str, *, confidence: float = 0.8,
               verification_state: str = "AUTO_EXTRACTED", sensitivity_tier: str = "PERSONAL",
               allowed_providers: list[str] | None = None, blocked_providers: list[str] | None = None,
               ephemeral_redaction: bool = False, valid_from: str | None = None,
               source_conversation_id: str | None = None, source_message: str | None = None,
               extracted_by_model: str | None = None, source_message_hash: str | None = None) -> dict[str, Any]:
        namespace, slot_key = _normalize_namespace(namespace), _normalize_key(slot_key)
        value = str(value).strip()
        if not value or len(value) > 4000:
            raise ValueError("value must contain 1 to 4000 characters")
        confidence = float(confidence)
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        verification_state = str(verification_state).upper()
        if verification_state not in {"AUTO_EXTRACTED", "USER_CONFIRMED", "PINNED", "PENDING_CONFIRMATION"}:
            raise ValueError("unsupported verification_state")
        sensitivity_tier = str(sensitivity_tier).upper()
        if sensitivity_tier not in {"PUBLIC", "PERSONAL", "INTERNAL", "CONFIDENTIAL", "SECRET"}:
            raise ValueError("unsupported sensitivity_tier")
        allow = sorted(set(allowed_providers or []))
        block = sorted(set(blocked_providers or []))
        if any(not _PROVIDERS.fullmatch(provider) for provider in allow + block):
            raise ValueError("provider names may contain letters, numbers, '.', '_' and '-' only")
        now = _utc_now()
        start = _normalize_timestamp(valid_from) if valid_from else now
        parsed_start = datetime.fromisoformat(start.replace("Z", "+00:00"))
        source_hash = source_message_hash or (hashlib.sha256(source_message.encode("utf-8")).hexdigest() if source_message else None)
        source_quote = source_message[:2000] if source_message else None
        memory_id = "mem_" + uuid.uuid4().hex
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            latest = db.execute("""
                SELECT e.* FROM ledger_events e JOIN
                (SELECT memory_id,MAX(seq) seq FROM ledger_events WHERE user_id=? GROUP BY memory_id) x
                ON x.memory_id=e.memory_id AND x.seq=e.seq
                WHERE e.user_id=? AND e.namespace=? AND e.slot_key=?
                ORDER BY e.seq DESC LIMIT 1
            """, (self.user_id, self.user_id, namespace, slot_key)).fetchone()
            if latest and latest["status"] == "DELETED" and verification_state not in {"USER_CONFIRMED", "PINNED"}:
                db.execute("ROLLBACK")
                raise ValueError("this slot was deleted by the user; automatic extraction cannot restore it")
            supersedes_id = latest["memory_id"] if latest else None
            if latest:
                old = self._row(latest)
                if old["status"] == "ACTIVE" and (old["value"] == value and old["allowed_providers"] == allow
                    and old["blocked_providers"] == block and old["ephemeral_redaction"] == ephemeral_redaction
                    and old["sensitivity_tier"] == sensitivity_tier
                    and old["verification_state"] == verification_state and old["confidence"] == confidence):
                    db.execute("ROLLBACK")
                    return old
                old_start = datetime.fromisoformat(old["valid_from"].replace("Z", "+00:00"))
                if old["status"] == "ACTIVE" and parsed_start < old_start:
                    db.execute("ROLLBACK")
                    raise ValueError("a replacement fact cannot start before the active fact's valid_from")
                if old["status"] == "ACTIVE":
                    self._append_state(db, memory_id=old["id"], user_id=self.user_id, event_type="SUPERSEDE",
                        namespace=old["namespace"], slot_key=old["slot_key"], value=old["value"], status="SUPERSEDED",
                        confidence=old["confidence"], verification_state=old["verification_state"],
                        sensitivity_tier=old["sensitivity_tier"], allowed_providers=old["allowed_providers"],
                        blocked_providers=old["blocked_providers"], ephemeral_redaction=old["ephemeral_redaction"],
                        valid_from=old["valid_from"], valid_to=start, recorded_at=now,
                        source_conversation_id=old["source_conversation_id"], source_quote=old["source_quote"],
                        source_message_hash=old["source_message_hash"],
                        extracted_by_model=old["extracted_by_model"], supersedes_id=None)
            self._append_state(db, memory_id=memory_id, user_id=self.user_id, event_type="SET",
                namespace=namespace, slot_key=slot_key, value=value, status="ACTIVE", confidence=confidence,
                verification_state=verification_state, sensitivity_tier=sensitivity_tier,
                allowed_providers=allow, blocked_providers=block, ephemeral_redaction=ephemeral_redaction,
                valid_from=start, valid_to=None, recorded_at=now,
                source_conversation_id=source_conversation_id, source_quote=source_quote, source_message_hash=source_hash,
                extracted_by_model=extracted_by_model, supersedes_id=supersedes_id)
            db.execute("COMMIT")
        return self.get(memory_id)

    def get(self, memory_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("""
                SELECT e.* FROM ledger_events e JOIN
                (SELECT memory_id,MAX(seq) seq FROM ledger_events WHERE user_id=? AND memory_id=? GROUP BY memory_id) x
                ON x.memory_id=e.memory_id AND x.seq=e.seq
            """, (self.user_id, memory_id)).fetchone()
        return self._row(row) if row else None

    def slot_state(self, namespace: str, slot_key: str) -> dict[str, Any] | None:
        namespace, slot_key = _normalize_namespace(namespace), _normalize_key(slot_key)
        with self._connect() as db:
            row = db.execute("""
                SELECT e.* FROM ledger_events e JOIN
                (SELECT memory_id,MAX(seq) seq FROM ledger_events WHERE user_id=? GROUP BY memory_id) x
                ON x.memory_id=e.memory_id AND x.seq=e.seq
                WHERE e.user_id=? AND e.namespace=? AND e.slot_key=?
                ORDER BY e.seq DESC LIMIT 1
            """, (self.user_id, self.user_id, namespace, slot_key)).fetchone()
        return self._row(row) if row else None

    def edit(self, memory_id: str, *, value: str | None = None, pinned: bool | None = None) -> dict[str, Any] | None:
        current = self.get(memory_id)
        if not current or current["status"] != "ACTIVE":
            return None
        verification = "PINNED" if pinned is True else (
            "USER_CONFIRMED" if pinned is False or value is not None else current["verification_state"])
        return self.record(current["namespace"], current["slot_key"], value if value is not None else current["value"],
            confidence=current["confidence"], verification_state=verification,
            sensitivity_tier=current["sensitivity_tier"], allowed_providers=current["allowed_providers"],
            blocked_providers=current["blocked_providers"], ephemeral_redaction=current["ephemeral_redaction"],
            valid_from=current["valid_from"], source_conversation_id=current["source_conversation_id"],
            source_message=current.get("source_quote"), extracted_by_model=current["extracted_by_model"],
            source_message_hash=current["source_message_hash"])

    def delete(self, memory_id: str) -> dict[str, Any] | None:
        current = self.get(memory_id)
        if not current or current["status"] in {"DELETED", "REJECTED"}:
            return None
        if current["status"] == "SUPERSEDED":
            with self._connect() as db:
                db.execute("DELETE FROM ledger_events WHERE user_id=? AND memory_id=?", (self.user_id, current["id"]))
            return {"id": current["id"], "status": "PURGED"}
        now = _utc_now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # Forget means removing the plaintext and provenance from this vault.
            # Keep only a slot-level tombstone so old summaries cannot silently
            # repopulate the same slot through automatic extraction.
            db.execute("DELETE FROM ledger_events WHERE user_id=? AND memory_id=?", (self.user_id, current["id"]))
            self._append_state(db, memory_id=current["id"], user_id=self.user_id, event_type="TOMBSTONE",
                namespace=current["namespace"], slot_key=current["slot_key"], value="", status="DELETED",
                confidence=current["confidence"], verification_state=current["verification_state"],
                sensitivity_tier=current["sensitivity_tier"], allowed_providers=current["allowed_providers"],
                blocked_providers=current["blocked_providers"], ephemeral_redaction=current["ephemeral_redaction"],
                valid_from=current["valid_from"], valid_to=now, recorded_at=now,
                source_conversation_id=None, source_quote=None, source_message_hash=None,
                extracted_by_model=None, supersedes_id=None)
            db.execute("COMMIT")
        return self.get(memory_id)

    def list(self, *, include_history: bool = False, status: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as db:
            if include_history:
                rows = db.execute("SELECT * FROM ledger_events WHERE user_id=? ORDER BY seq DESC", (self.user_id,)).fetchall()
            else:
                rows = self._latest_rows(db, self.user_id)
        records = [self._row(row) for row in rows]
        if status:
            records = [record for record in records if record["status"] == status.upper()]
        return records

    def as_of(self, namespace: str, slot_key: str, when: str, *, known_at: str | None = None) -> dict[str, Any] | None:
        namespace, slot_key = _normalize_namespace(namespace), _normalize_key(slot_key)
        when = _normalize_timestamp(when)
        knowledge_time = _normalize_timestamp(known_at) if known_at else _utc_now()
        with self._connect() as db:
            rows = db.execute("""
                SELECT e.* FROM ledger_events e JOIN
                (SELECT memory_id,MAX(seq) seq FROM ledger_events WHERE user_id=? AND recorded_at<=? GROUP BY memory_id) x
                ON x.memory_id=e.memory_id AND x.seq=e.seq
                WHERE e.user_id=? AND e.namespace=? AND e.slot_key=? AND e.status IN ('ACTIVE','SUPERSEDED','DELETED')
                  AND e.valid_from<=? AND (e.valid_to IS NULL OR ?<e.valid_to) AND e.recorded_at<=?
                ORDER BY e.valid_from DESC LIMIT 1
            """, (self.user_id, knowledge_time, self.user_id, namespace, slot_key, when, when, knowledge_time)).fetchone()
        return self._row(rows) if rows else None

    def _records_at(self, when: str, known_at: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("""
                SELECT e.* FROM ledger_events e JOIN
                (SELECT memory_id,MAX(seq) seq FROM ledger_events WHERE user_id=? AND recorded_at<=? GROUP BY memory_id) x
                ON x.memory_id=e.memory_id AND x.seq=e.seq
                WHERE e.user_id=? AND e.status IN ('ACTIVE','SUPERSEDED','DELETED')
                  AND e.valid_from<=? AND (e.valid_to IS NULL OR ?<e.valid_to)
            """, (self.user_id, known_at, self.user_id, when, when)).fetchall()
        records = [self._row(row) for row in rows]
        latest_by_slot: dict[tuple[str, str], dict[str, Any]] = {}
        for record in records:
            key = (record["namespace"], record["slot_key"])
            previous = latest_by_slot.get(key)
            if previous is None or record["valid_from"] > previous["valid_from"]:
                latest_by_slot[key] = record
        return list(latest_by_slot.values())

    def propose(self, namespace: str, slot_key: str, value: str, **policy: Any) -> str:
        value = str(value).strip()
        if not value or len(value) > 4000:
            raise ValueError("proposed value must contain 1 to 4000 characters")
        allowed = {"confidence", "sensitivity_tier", "allowed_providers", "blocked_providers",
                   "ephemeral_redaction", "valid_from", "source_conversation_id", "source_message",
                   "extracted_by_model"}
        if set(policy) - allowed:
            raise ValueError("proposal contains unsupported policy fields")
        proposal_id = "prp_" + uuid.uuid4().hex
        payload = {"namespace": _normalize_namespace(namespace), "slot_key": _normalize_key(slot_key),
                   "value": value, "policy": policy}
        if "confidence" in policy and not 0.0 <= float(policy["confidence"]) <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        with self._connect() as db:
            db.execute("INSERT INTO pending_proposals VALUES(?,?,?,?,?,NULL)",
                       (proposal_id, self.user_id, json.dumps(payload, ensure_ascii=False), "PENDING", _utc_now()))
        return proposal_id

    def proposals(self, *, status: str = "PENDING") -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM pending_proposals WHERE user_id=? AND status=? ORDER BY created_at DESC",
                              (self.user_id, status.upper())).fetchall()
        return [{"proposal_id": row["proposal_id"], "proposal": json.loads(row["proposal_json"]),
                 "status": row["status"], "created_at": row["created_at"]} for row in rows]

    def resolve_proposal(self, proposal_id: str, *, approve: bool) -> dict[str, Any] | None:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM pending_proposals WHERE proposal_id=? AND user_id=? AND status='PENDING'",
                             (proposal_id, self.user_id)).fetchone()
            if not row:
                db.execute("ROLLBACK")
                return None
            proposal = json.loads(row["proposal_json"])
            db.execute("UPDATE pending_proposals SET status=?,resolved_at=? WHERE proposal_id=? AND user_id=?",
                       ("APPROVED" if approve else "REJECTED", _utc_now(), proposal_id, self.user_id))
            db.execute("COMMIT")
        if not approve:
            return {"proposal_id": proposal_id, "status": "REJECTED"}
        policy = proposal.get("policy") or {}
        policy["verification_state"] = "USER_CONFIRMED"
        result = self.record(proposal["namespace"], proposal["slot_key"], proposal["value"], **policy)
        return {"proposal_id": proposal_id, "status": "APPROVED", "memory": result}

    def context(self, query: str, *, provider: str, token_budget: int = 900,
                as_of: str | None = None, namespace: str | None = None) -> dict[str, Any]:
        """Compile allowed current state into compact deterministic key/value context."""
        if not _PROVIDERS.fullmatch(provider):
            raise ValueError("provider is required and must be a provider identifier")
        if token_budget < 1 or token_budget > 100_000:
            raise ValueError("token_budget must be between 1 and 100000")
        timestamp = _normalize_timestamp(as_of) if as_of else _utc_now()
        records = self._records_at(timestamp, _utc_now()) if as_of else self.list()
        local_provider = provider.casefold() in {"local", "ollama", "local_ollama", "nexor_local"}
        eligible = []
        query_terms = _terms(query)
        for record in records:
            if record["status"] in {"DELETED", "REJECTED"}:
                continue
            if not (record["valid_from"] <= timestamp and (record["valid_to"] is None or timestamp < record["valid_to"])):
                continue
            if namespace and record["namespace"] != _normalize_namespace(namespace):
                continue
            if record["allowed_providers"] and provider not in record["allowed_providers"]:
                continue
            if provider in record["blocked_providers"]:
                continue
            if record["sensitivity_tier"] == "SECRET" and not local_provider:
                continue
            if record["sensitivity_tier"] in {"INTERNAL", "CONFIDENTIAL"} and not local_provider and provider not in record["allowed_providers"]:
                continue
            if provider.casefold() == "auto" and record["sensitivity_tier"] in {"INTERNAL", "CONFIDENTIAL"}:
                continue
            record_terms = _terms(record["namespace"] + " " + record["slot_key"] + " " + record["value"])
            overlap = len(query_terms & record_terms) / max(1, len(query_terms))
            if query_terms and overlap == 0:
                continue
            eligible.append((overlap, record))
        eligible.sort(key=lambda item: (-item[0], item[1]["namespace"], item[1]["slot_key"], item[1]["id"]))

        lines: list[str] = ["# nexor-memory-v1"]
        citations: list[dict[str, Any]] = []
        redactions: dict[str, str] = {}
        char_limit = token_budget * 4
        used = len(lines[0])
        for _, record in eligible:
            value = record["value"]
            if record["ephemeral_redaction"]:
                placeholder = "[MEMORY_" + record["id"][4:].upper() + "]"
                redactions[placeholder] = value
                value = placeholder
            line = f"{record['namespace']}.{record['slot_key']}={json.dumps(value, ensure_ascii=False)}"
            if used + len(line) + 1 > char_limit:
                continue
            lines.append(line)
            used += len(line) + 1
            citations.append({"id": record["id"], "namespace": record["namespace"],
                              "slot_key": record["slot_key"], "source_conversation_id": record["source_conversation_id"],
                              "source_message_hash": record["source_message_hash"],
                              "context_value": value,
                              "verification_state": record["verification_state"]})
        return {"text": "\n".join(lines) if citations else "", "citations": citations,
                "redactions": redactions, "provider": provider, "as_of": timestamp,
                "approx_tokens": (used + 3) // 4 if citations else 0,
                "eligible_count": len(eligible), "injected_count": len(citations)}

    @staticmethod
    def rehydrate(text: str, redactions: dict[str, str]) -> str:
        for placeholder, original in redactions.items():
            text = text.replace(placeholder, original)
        return text

    def export_payload(self) -> dict[str, Any]:
        return {"format": self.FORMAT, "schema_version": SCHEMA_VERSION, "user_id": self.user_id,
                "exported_at": _utc_now(), "events": self.export_events(),
                "proposals": self.proposals(status="PENDING")}

    def export_events(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM ledger_events WHERE user_id=? ORDER BY seq", (self.user_id,)).fetchall()
        return [{"event_id": row["event_id"], "memory_id": row["memory_id"], "event_type": row["event_type"],
                 **self._row(row)} for row in rows]

    def import_payload(self, payload: dict[str, Any], *, merge: bool = True) -> int:
        if payload.get("format") != self.FORMAT or int(payload.get("schema_version", 0)) > SCHEMA_VERSION:
            raise ValueError("unsupported or newer vault format")
        events = payload.get("events")
        if not isinstance(events, list):
            raise ValueError("vault events must be a list")
        for event in events:
            required = ("event_id", "id", "namespace", "slot_key", "value", "status", "valid_from", "recorded_at", "content_hash")
            if not isinstance(event, dict) or any(key not in event for key in required):
                raise ValueError("invalid ledger event")
        added = 0
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not merge:
                db.execute("DELETE FROM ledger_events WHERE user_id=?", (self.user_id,))
                db.execute("DELETE FROM pending_proposals WHERE user_id=?", (self.user_id,))
            tombstones = {(row["namespace"], row["slot_key"]) for row in self._latest_rows(db, self.user_id)
                          if row["status"] == "DELETED"}
            for event in events:
                if not isinstance(event.get("id"), str) or not event["id"].startswith("mem_"):
                    raise ValueError("invalid memory id in ledger event")
                new_event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, self.user_id + ":" + str(event["event_id"])))
                existing = db.execute("SELECT 1 FROM ledger_events WHERE event_id=?", (new_event_id,)).fetchone()
                if existing:
                    continue
                # Imported facts are always scoped to the receiving vault, never the source user id.
                memory_id = event["id"]
                namespace, slot_key = _normalize_namespace(event["namespace"]), _normalize_key(event["slot_key"])
                if (namespace, slot_key) in tombstones and event["status"] in {"ACTIVE", "SUPERSEDED"}:
                    continue
                fields = (event.get("event_type", "IMPORT"), _normalize_namespace(event["namespace"]),
                          slot_key, str(event["value"]), str(event["status"]),
                          float(event.get("confidence", 0.8)), str(event.get("verification_state", "AUTO_EXTRACTED")),
                          str(event.get("sensitivity_tier", "PERSONAL")),
                          sorted(set(event.get("allowed_providers", []))), sorted(set(event.get("blocked_providers", []))),
                          bool(event.get("ephemeral_redaction", False)), _normalize_timestamp(event["valid_from"]),
                          _normalize_timestamp(event["valid_to"]) if event.get("valid_to") else None,
                          _normalize_timestamp(event["recorded_at"]), event.get("source_conversation_id"),
                          event.get("source_quote"), event.get("source_message_hash"),
                          event.get("extracted_by_model"), event.get("supersedes_id"))
                digest = hashlib.sha256(_canonical({"source_hash": event["content_hash"], "receiving_user": self.user_id})).hexdigest()
                db.execute("""
                    INSERT INTO ledger_events(event_id,memory_id,user_id,event_type,namespace,slot_key,value,status,
                        confidence,verification_state,sensitivity_tier,allowed_providers_json,blocked_providers_json,
                        ephemeral_redaction,valid_from,valid_to,recorded_at,source_conversation_id,source_quote,source_message_hash,
                        extracted_by_model,supersedes_id,payload_hash,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (new_event_id, memory_id, self.user_id, *fields[:11], fields[11], fields[12], fields[13],
                      fields[14], fields[15], fields[16], fields[17], fields[18], digest, _utc_now()))
                added += 1
            for proposal in payload.get("proposals", []):
                if not isinstance(proposal, dict) or not isinstance(proposal.get("proposal_id"), str):
                    continue
                proposal_id = str(uuid.uuid5(uuid.NAMESPACE_URL, self.user_id + ":proposal:" + proposal["proposal_id"]))
                if db.execute("SELECT 1 FROM pending_proposals WHERE proposal_id=?", (proposal_id,)).fetchone():
                    continue
                proposal_value = proposal.get("proposal")
                if isinstance(proposal_value, dict):
                    db.execute("INSERT INTO pending_proposals VALUES(?,?,?,?,?,NULL)",
                        (proposal_id, self.user_id, json.dumps(proposal_value, ensure_ascii=False), "PENDING",
                         _normalize_timestamp(proposal.get("created_at") or _utc_now())))
            db.execute("COMMIT")
        return added
