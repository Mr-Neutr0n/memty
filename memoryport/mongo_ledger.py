"""MongoDB event-ledger backend using the dedicated memory_vault_ledger collection.

The collection contains current-state projections, immutable event snapshots,
slot pointers, and pending proposals. Writes use MongoDB transactions, so use a
replica set such as MongoDB Atlas for this backend.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from threading import RLock
from typing import Any

from .ledger import MemoryLedger, SCHEMA_VERSION, _PROVIDERS, _canonical, _normalize_key, _normalize_namespace, _normalize_timestamp, _utc_now


_CLIENTS: dict[str, Any] = {}
_CLIENT_LOCK = RLock()


class MongoMemoryLedger(MemoryLedger):
    """The same vault operations backed by MongoDB instead of a local SQLite file."""

    def __init__(self, uri: str, user_id: str, *, database: str = "Memory",
                 collection: str = "memory_vault_ledger"):
        if not uri or not user_id:
            raise ValueError("MongoDB URI and authenticated user_id are required")
        try:
            from pymongo import MongoClient
        except ImportError as error:
            raise RuntimeError("MongoDB vault support requires: pip install 'nexorai-smart-auto[mongodb]'") from error
        self.user_id = str(user_id)
        with _CLIENT_LOCK:
            self._client = _CLIENTS.get(uri)
            if self._client is None:
                self._client = MongoClient(uri, serverSelectionTimeoutMS=5000, retryWrites=True)
                _CLIENTS[uri] = self._client
        self._collection = self._client[database][collection]
        self._collection.create_index([("user_id", 1), ("doc_type", 1), ("namespace", 1), ("slot_key", 1)])
        self._collection.create_index([("user_id", 1), ("doc_type", 1), ("memory_id", 1), ("seq", -1)])
        self._collection.create_index([("user_id", 1), ("doc_type", 1), ("status", 1), ("created_at", -1)])
        self._collection.create_index([("user_id", 1), ("doc_type", 1), ("seq", 1)])

    def _slot_id(self, namespace: str, slot_key: str) -> str:
        digest = hashlib.sha256(f"{self.user_id}\0{namespace}\0{slot_key}".encode()).hexdigest()
        return "slot:" + digest

    @staticmethod
    def _event_snapshot(record: dict[str, Any], event_type: str) -> dict[str, Any]:
        snapshot = dict(record)
        snapshot["event_id"] = str(uuid.uuid4())
        snapshot["event_type"] = event_type
        snapshot["content_hash"] = hashlib.sha256(_canonical({k: v for k, v in record.items() if k != "content_hash"})).hexdigest()
        return snapshot

    def _append_event(self, record: dict[str, Any], event_type: str, session: Any) -> dict[str, Any]:
        snapshot = self._event_snapshot(record, event_type)
        self._collection.insert_one({"_id": "event:" + snapshot["event_id"], "doc_type": "event",
                                     "user_id": self.user_id, "memory_id": snapshot["id"],
                                     "seq": time.time_ns(), "record": snapshot, "created_at": _utc_now()},
                                    session=session)
        return snapshot

    def _current(self, memory_id: str, session: Any = None) -> dict[str, Any] | None:
        row = self._collection.find_one({"doc_type": "state", "user_id": self.user_id, "memory_id": memory_id},
                                        session=session)
        return row.get("record") if row else None

    def record(self, namespace: str, slot_key: str, value: str, *, confidence: float = 0.8,
               verification_state: str = "AUTO_EXTRACTED", sensitivity_tier: str = "PERSONAL",
               allowed_providers: list[str] | None = None, blocked_providers: list[str] | None = None,
               ephemeral_redaction: bool = False, valid_from: str | None = None,
               source_conversation_id: str | None = None, source_message: str | None = None,
               source_message_hash: str | None = None,
               extracted_by_model: str | None = None) -> dict[str, Any]:
        namespace, slot_key = _normalize_namespace(namespace), _normalize_key(slot_key)
        value = str(value).strip()
        if not value or len(value) > 4000:
            raise ValueError("value must contain 1 to 4000 characters")
        confidence = float(confidence)
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        verification_state = str(verification_state).upper()
        if verification_state not in {"AUTO_EXTRACTED", "USER_CONFIRMED", "PINNED", "PENDING_CONFIRMATION"}:
            raise ValueError("unsupported verification_state")
        sensitivity_tier = str(sensitivity_tier).upper()
        if sensitivity_tier not in {"PUBLIC", "PERSONAL", "INTERNAL", "CONFIDENTIAL", "SECRET"}:
            raise ValueError("unsupported sensitivity_tier")
        allowed = sorted(set(allowed_providers or []))
        blocked = sorted(set(blocked_providers or []))
        if any(not isinstance(item, str) or not _PROVIDERS.fullmatch(item) for item in allowed + blocked):
            raise ValueError("provider names may contain letters, numbers, '.', '_' and '-' only")
        now = _utc_now()
        start = _normalize_timestamp(valid_from) if valid_from else now
        source_hash = source_message_hash or (hashlib.sha256(source_message.encode()).hexdigest() if source_message else None)
        memory_id = "mem_" + uuid.uuid4().hex
        slot_id = self._slot_id(namespace, slot_key)

        with self._client.start_session() as session:
            with session.start_transaction():
                slot = self._collection.find_one({"_id": slot_id, "user_id": self.user_id}, session=session)
                previous = self._current(slot["memory_id"], session) if slot and slot.get("memory_id") else None
                if previous and previous["status"] == "DELETED" and verification_state not in {"USER_CONFIRMED", "PINNED"}:
                    raise ValueError("this slot was deleted by the user; automatic extraction cannot restore it")
                if previous and previous["status"] == "ACTIVE":
                    if (previous["value"] == value and previous["allowed_providers"] == allowed
                        and previous["blocked_providers"] == blocked and previous["sensitivity_tier"] == sensitivity_tier
                        and previous["verification_state"] == verification_state
                        and previous["ephemeral_redaction"] == ephemeral_redaction
                        and previous["confidence"] == confidence):
                        return previous
                    old_start = _normalize_timestamp(previous["valid_from"])
                    if start < old_start:
                        raise ValueError("a replacement fact cannot start before the active fact's valid_from")
                    old = {**previous, "status": "SUPERSEDED", "valid_to": start, "recorded_at": now}
                    self._collection.update_one({"_id": "state:" + previous["id"], "user_id": self.user_id},
                        {"$set": {"record": old}}, session=session)
                    self._append_event(old, "SUPERSEDE", session)

                record = {"id": memory_id, "namespace": namespace, "slot_key": slot_key, "value": value,
                    "status": "ACTIVE", "confidence": confidence, "verification_state": verification_state,
                    "sensitivity_tier": sensitivity_tier, "allowed_providers": allowed, "blocked_providers": blocked,
                    "ephemeral_redaction": bool(ephemeral_redaction), "valid_from": start, "valid_to": None,
                    "recorded_at": now, "source_conversation_id": source_conversation_id,
                    "source_quote": source_message[:2000] if source_message else None,
                    "source_message_hash": source_hash, "extracted_by_model": extracted_by_model,
                    "supersedes_id": previous["id"] if previous else None}
                snapshot = self._append_event(record, "SET", session)
                self._collection.insert_one({"_id": "state:" + memory_id, "doc_type": "state",
                    "user_id": self.user_id, "memory_id": memory_id, "namespace": namespace,
                    "slot_key": slot_key, "status": "ACTIVE", "record": snapshot}, session=session)
                self._collection.replace_one({"_id": slot_id, "user_id": self.user_id},
                    {"_id": slot_id, "doc_type": "slot", "user_id": self.user_id,
                     "namespace": namespace, "slot_key": slot_key, "memory_id": memory_id,
                     "status": "ACTIVE", "updated_at": now}, upsert=True, session=session)
        return snapshot

    def get(self, memory_id: str) -> dict[str, Any] | None:
        return self._current(memory_id)

    def slot_state(self, namespace: str, slot_key: str) -> dict[str, Any] | None:
        namespace, slot_key = _normalize_namespace(namespace), _normalize_key(slot_key)
        slot = self._collection.find_one({"_id": self._slot_id(namespace, slot_key), "user_id": self.user_id})
        return self._current(slot["memory_id"]) if slot and slot.get("memory_id") else None

    def delete(self, memory_id: str) -> dict[str, Any] | None:
        current = self.get(memory_id)
        if not current or current["status"] in {"DELETED", "REJECTED"}:
            return None
        slot_id = self._slot_id(current["namespace"], current["slot_key"])
        with self._client.start_session() as session:
            with session.start_transaction():
                if current["status"] == "SUPERSEDED":
                    self._collection.delete_one({"_id": "state:" + memory_id, "user_id": self.user_id}, session=session)
                    self._collection.delete_many({"doc_type": "event", "user_id": self.user_id, "memory_id": memory_id}, session=session)
                    return {"id": memory_id, "status": "PURGED"}
                tombstone = {**current, "value": "", "status": "DELETED", "valid_to": _utc_now(),
                             "recorded_at": _utc_now(), "source_conversation_id": None,
                             "source_quote": None, "source_message_hash": None, "extracted_by_model": None}
                self._collection.delete_many({"doc_type": "event", "user_id": self.user_id, "memory_id": memory_id}, session=session)
                snapshot = self._append_event(tombstone, "TOMBSTONE", session)
                self._collection.update_one({"_id": "state:" + memory_id, "user_id": self.user_id},
                    {"$set": {"record": snapshot, "status": "DELETED"}}, session=session)
                self._collection.update_one({"_id": slot_id, "user_id": self.user_id},
                    {"$set": {"memory_id": memory_id, "status": "DELETED", "updated_at": _utc_now()}}, session=session)
        return snapshot

    def list(self, *, include_history: bool = False, status: str | None = None) -> list[dict[str, Any]]:
        if include_history:
            records = [row["record"] for row in self._collection.find(
                {"doc_type": "event", "user_id": self.user_id}).sort("seq", -1)]
        else:
            records = [row["record"] for row in self._collection.find(
                {"doc_type": "state", "user_id": self.user_id})]
        if status:
            records = [record for record in records if record["status"] == status.upper()]
        return records

    def _records_at(self, when: str, known_at: str) -> list[dict[str, Any]]:
        pipeline = [
            {"$match": {"doc_type": "event", "user_id": self.user_id,
                        "record.recorded_at": {"$lte": known_at}}},
            {"$sort": {"seq": 1}},
            {"$group": {"_id": "$memory_id", "record": {"$last": "$record"}}},
        ]
        latest_records = [row["record"] for row in self._collection.aggregate(pipeline)]
        matches = [record for record in latest_records
                   if record["status"] in {"ACTIVE", "SUPERSEDED"}
                   and record["valid_from"] <= when
                   and (record["valid_to"] is None or when < record["valid_to"])]
        by_slot: dict[tuple[str, str], dict[str, Any]] = {}
        for record in matches:
            key = (record["namespace"], record["slot_key"])
            if key not in by_slot or record["valid_from"] > by_slot[key]["valid_from"]:
                by_slot[key] = record
        return list(by_slot.values())

    def as_of(self, namespace: str, slot_key: str, when: str, *, known_at: str | None = None) -> dict[str, Any] | None:
        namespace, slot_key = _normalize_namespace(namespace), _normalize_key(slot_key)
        when, knowledge_time = _normalize_timestamp(when), _normalize_timestamp(known_at) if known_at else _utc_now()
        for record in self._records_at(when, knowledge_time):
            if record["namespace"] == namespace and record["slot_key"] == slot_key:
                return record
        return None

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
        self._collection.insert_one({"_id": "proposal:" + proposal_id, "doc_type": "proposal",
            "user_id": self.user_id, "proposal_id": proposal_id, "proposal": payload,
            "status": "PENDING", "created_at": _utc_now()})
        return proposal_id

    def proposals(self, *, status: str = "PENDING") -> list[dict[str, Any]]:
        return [{"proposal_id": row["proposal_id"], "proposal": row["proposal"],
                 "status": row["status"], "created_at": row["created_at"]}
                for row in self._collection.find({"doc_type": "proposal", "user_id": self.user_id,
                                                   "status": status.upper()}).sort("created_at", -1)]

    def resolve_proposal(self, proposal_id: str, *, approve: bool) -> dict[str, Any] | None:
        row = self._collection.find_one_and_update(
            {"_id": "proposal:" + proposal_id, "user_id": self.user_id, "status": "PENDING"},
            {"$set": {"status": "APPROVED" if approve else "REJECTED", "resolved_at": _utc_now()}},
            return_document=True)
        if not row:
            return None
        if not approve:
            return {"proposal_id": proposal_id, "status": "REJECTED"}
        proposal = row["proposal"]
        policy = dict(proposal.get("policy") or {})
        policy["verification_state"] = "USER_CONFIRMED"
        result = self.record(proposal["namespace"], proposal["slot_key"], proposal["value"], **policy)
        return {"proposal_id": proposal_id, "status": "APPROVED", "memory": result}

    def export_events(self) -> list[dict[str, Any]]:
        return [row["record"] for row in self._collection.find(
            {"doc_type": "event", "user_id": self.user_id}).sort("seq", 1)]

    def export_payload(self) -> dict[str, Any]:
        return {"format": self.FORMAT, "schema_version": SCHEMA_VERSION, "user_id": self.user_id,
                "exported_at": _utc_now(), "events": self.export_events(), "proposals": self.proposals()}

    def import_payload(self, payload: dict[str, Any], *, merge: bool = True) -> int:
        if payload.get("format") != self.FORMAT or int(payload.get("schema_version", 0)) > SCHEMA_VERSION:
            raise ValueError("unsupported or newer vault format")
        events = payload.get("events")
        if not isinstance(events, list):
            raise ValueError("vault events must be a list")
        for event in events:
            if not isinstance(event, dict) or not all(key in event for key in ("event_id", "id", "namespace", "slot_key", "value", "status")):
                raise ValueError("invalid ledger event")

        added = 0
        with self._client.start_session() as session:
            with session.start_transaction():
                if not merge:
                    self._collection.delete_many({"user_id": self.user_id}, session=session)
                blocked_slots = set()
                if merge:
                    blocked_slots = {row["_id"] for row in self._collection.find(
                        {"doc_type": "slot", "user_id": self.user_id, "status": {"$in": ["ACTIVE", "DELETED"]}},
                        {"_id": 1}, session=session)}
                latest_memory: dict[str, tuple[int, dict[str, Any]]] = {}
                latest_slot: dict[str, tuple[int, dict[str, Any]]] = {}
                for index, event in enumerate(events):
                    namespace, slot_key = _normalize_namespace(event["namespace"]), _normalize_key(event["slot_key"])
                    slot_id = self._slot_id(namespace, slot_key)
                    if slot_id in blocked_slots and event["status"] in {"ACTIVE", "SUPERSEDED"}:
                        continue
                    imported_event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, self.user_id + ":" + str(event["event_id"])))
                    mongo_event_id = "event:" + imported_event_id
                    if self._collection.find_one({"_id": mongo_event_id, "user_id": self.user_id}, {"_id": 1}, session=session):
                        continue
                    record = dict(event)
                    record["id"] = str(event["id"])
                    record["namespace"], record["slot_key"] = namespace, slot_key
                    record["valid_from"] = _normalize_timestamp(record["valid_from"])
                    if record.get("valid_to"):
                        record["valid_to"] = _normalize_timestamp(record["valid_to"])
                    record["recorded_at"] = _normalize_timestamp(record.get("recorded_at") or _utc_now())
                    seq = time.time_ns() + index
                    self._collection.insert_one({"_id": mongo_event_id, "doc_type": "event", "user_id": self.user_id,
                        "memory_id": record["id"], "seq": seq, "record": record, "created_at": _utc_now()}, session=session)
                    if record["id"] not in latest_memory or seq > latest_memory[record["id"]][0]:
                        latest_memory[record["id"]] = (seq, record)
                    if slot_id not in latest_slot or seq > latest_slot[slot_id][0]:
                        latest_slot[slot_id] = (seq, record)
                    added += 1
                for memory_id, (_, record) in latest_memory.items():
                    self._collection.replace_one({"_id": "state:" + memory_id, "user_id": self.user_id},
                        {"_id": "state:" + memory_id, "doc_type": "state", "user_id": self.user_id,
                         "memory_id": memory_id, "namespace": record["namespace"], "slot_key": record["slot_key"],
                         "status": record["status"], "record": record}, upsert=True, session=session)
                for slot_id, (_, record) in latest_slot.items():
                    if slot_id in blocked_slots:
                        continue
                    self._collection.replace_one({"_id": slot_id, "user_id": self.user_id},
                        {"_id": slot_id, "doc_type": "slot", "user_id": self.user_id,
                         "namespace": record["namespace"], "slot_key": record["slot_key"],
                         "memory_id": record["id"], "status": record["status"], "updated_at": record["recorded_at"]},
                        upsert=True, session=session)
                for proposal in payload.get("proposals", []):
                    if not isinstance(proposal, dict) or not isinstance(proposal.get("proposal_id"), str):
                        continue
                    proposal_id = str(uuid.uuid5(uuid.NAMESPACE_URL, self.user_id + ":proposal:" + proposal["proposal_id"]))
                    self._collection.update_one({"_id": "proposal:" + proposal_id}, {"$setOnInsert": {
                        "doc_type": "proposal", "user_id": self.user_id, "proposal_id": proposal_id,
                        "proposal": proposal.get("proposal", {}), "status": "PENDING",
                        "created_at": _normalize_timestamp(proposal.get("created_at") or _utc_now())}},
                        upsert=True, session=session)
        return added

