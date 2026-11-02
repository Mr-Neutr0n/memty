"""A small, provider-independent JSON memory store.

The store uses lexical ranking by default and cosine similarity when both the
query and entries have embeddings. Embeddings can be supplied by the host app;
this module never calls an embedding or model API itself.
"""

from __future__ import annotations

import json
import math
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def _terms(text: str) -> set[str]:
    return {word.lower() for word in re.findall(r"[\w'-]{2,}", text, re.UNICODE)}


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    norm = math.sqrt(sum(a * a for a in left) * sum(b * b for b in right))
    return dot / norm if norm else 0.0


class PortableMemoryStore:
    """JSON backed user memory with import/export and simple retrieval."""

    FORMAT = "nexor-portable-memory-v1"

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if payload.get("format") != self.FORMAT or not isinstance(payload.get("memories"), list):
            raise ValueError("Unsupported portable-memory file format")
        return payload["memories"]

    def _write(self, entries: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"format": self.FORMAT, "updated_at": datetime.now(timezone.utc).isoformat(), "memories": entries}
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, delete=False) as handle:
                temp_name = handle.name
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            Path(temp_name).replace(self.path)
        finally:
            if temp_name and Path(temp_name).exists():
                Path(temp_name).unlink()

    def add(self, fact: str, *, kind: str = "semantic", embedding: Iterable[float] | None = None,
            importance: float = 0.5, source: str = "") -> dict[str, Any]:
        text = str(fact).strip()
        if not 4 <= len(text) <= 2000:
            raise ValueError("Memory fact must contain 4 to 2000 characters")
        if kind not in {"semantic", "style", "episode"}:
            raise ValueError("kind must be semantic, style, or episode")
        vector = [float(value) for value in embedding] if embedding is not None else None
        if vector is not None and (not vector or not all(math.isfinite(value) for value in vector)):
            raise ValueError("embedding must contain finite numbers")
        entry = {"id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"), "fact": text,
                 "type": kind, "importance": max(0.0, min(1.0, float(importance))),
                 "source": str(source)[:200], "created_at": datetime.now(timezone.utc).isoformat(),
                 "embedding": vector}
        entries = self._read()
        entries.append(entry)
        self._write(entries)
        return {key: value for key, value in entry.items() if key != "embedding"}

    def retrieve(self, query: str, *, query_embedding: Iterable[float] | None = None,
                 limit: int = 8) -> list[dict[str, Any]]:
        query_words = _terms(query)
        vector = [float(value) for value in query_embedding] if query_embedding is not None else None
        ranked = []
        for entry in self._read():
            if entry.get("status", "active") != "active":
                continue
            fact = str(entry.get("fact", ""))
            fact_words = _terms(fact)
            lexical = len(query_words & fact_words) / max(1, len(query_words))
            semantic = _cosine(vector, entry.get("embedding") or []) if vector else 0.0
            score = max(lexical, max(0.0, semantic)) * 0.85 + float(entry.get("importance", 0.5)) * 0.15
            if score > 0.12:
                ranked.append((score, entry))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [{**{key: value for key, value in entry.items() if key != "embedding"}, "score": round(score, 4)}
                for score, entry in ranked[:max(0, limit)]]

    def export(self) -> dict[str, Any]:
        return {"format": self.FORMAT, "memories": self._read()}

    def import_data(self, payload: dict[str, Any], *, replace: bool = False) -> int:
        if payload.get("format") != self.FORMAT or not isinstance(payload.get("memories"), list):
            raise ValueError("Unsupported portable-memory file format")
        incoming = payload["memories"]
        if any(not isinstance(item, dict) or not isinstance(item.get("fact"), str) for item in incoming):
            raise ValueError("Every imported memory must contain a fact")
        current = [] if replace else self._read()
        seen = {item["fact"].strip().casefold() for item in current}
        for item in incoming:
            fact = item["fact"].strip()
            if fact and fact.casefold() not in seen:
                current.append({**item, "fact": fact})
                seen.add(fact.casefold())
        self._write(current)
        return len(current)


class MongoSyncedMemoryStore(PortableMemoryStore):
    """User-scoped adapter for Memty's existing MongoDB memory collection.

    MongoDB remains canonical. Every public read refreshes the JSON mirror;
    writes go to MongoDB first and then refresh the mirror. Install pymongo to
    use this optional adapter. Never reuse one instance across user IDs.
    """

    def __init__(self, uri: str, user_id: str, path: str | Path, *,
                 database: str = "Memory", collection: str = "user_memories"):
        if not uri or not user_id:
            raise ValueError("MongoDB URI and authenticated user_id are required")
        try:
            from bson import ObjectId
            from pymongo import MongoClient
        except ImportError as error:
            raise RuntimeError("Install the optional dependency with: pip install 'memty[mongodb]'") from error
        if not ObjectId.is_valid(user_id):
            raise ValueError("user_id must be the authenticated Memty MongoDB ObjectId")
        super().__init__(path)
        self._object_id = ObjectId(user_id)
        self._client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        self._collection = self._client[database][collection]

    def close(self) -> None:
        self._client.close()

    def sync(self) -> int:
        """Refresh the portable JSON snapshot from this user's Mongo records."""
        entries = []
        cursor = self._collection.find({"userId": self._object_id}).sort("updatedAt", -1)
        for doc in cursor:
            entries.append({
                "id": str(doc["_id"]), "fact": doc.get("fact", ""),
                "type": doc.get("type", "semantic"), "importance": doc.get("importance", 0.5),
                "confidence": doc.get("confidence", 0.8), "source": doc.get("sourceMessage", ""),
                "created_at": doc.get("createdAt").isoformat() if doc.get("createdAt") else None,
                "status": doc.get("status", "active"), "pinned": bool(doc.get("pinned", False)),
                "use_count": int(doc.get("useCount", 0)), "embedding": doc.get("embedding"),
            })
        self._write(entries)
        return len(entries)

    def _read(self) -> list[dict[str, Any]]:
        self.sync()
        return super()._read()

    def add(self, fact: str, *, kind: str = "semantic", embedding: Iterable[float] | None = None,
            importance: float = 0.5, source: str = "") -> dict[str, Any]:
        text = str(fact).strip()
        if not 4 <= len(text) <= 500:
            raise ValueError("Memty memory fact must contain 4 to 500 characters")
        if kind not in {"semantic", "style"}:
            raise ValueError("Memty memory type must be semantic or style")
        existing = self._collection.find_one({"userId": self._object_id, "status": "active", "type": kind,
                                               "fact": {"$regex": f"^{re.escape(text)}$", "$options": "i"}})
        if existing:
            self.sync()
            return {"id": str(existing["_id"]), "fact": existing["fact"], "type": existing["type"]}
        vector = [float(value) for value in embedding] if embedding is not None else None
        if vector is not None and (not vector or not all(math.isfinite(value) for value in vector)):
            raise ValueError("embedding must contain finite numbers")
        doc = {"userId": self._object_id, "fact": text, "type": kind,
               "confidence": 1.0, "importance": max(0.0, min(1.0, float(importance))),
               "sourceMessage": str(source)[:2000], "status": "active", "pinned": False,
               "useCount": 0, "lastUsedAt": datetime.now(timezone.utc)}
        if vector is not None:
            doc["embedding"] = vector
        result = self._collection.insert_one(doc)
        self.sync()
        return {"id": str(result.inserted_id), "fact": text, "type": kind}

    def import_data(self, payload: dict[str, Any], *, replace: bool = False) -> int:
        if replace:
            raise ValueError("Mongo synced imports are additive; use the Memty memory dashboard to delete records")
        if payload.get("format") != self.FORMAT or not isinstance(payload.get("memories"), list):
            raise ValueError("Unsupported portable-memory file format")
        for item in payload["memories"]:
            if not isinstance(item, dict) or not isinstance(item.get("fact"), str):
                raise ValueError("Every imported memory must contain a fact")
            fact = item["fact"].strip()
            if not fact or item.get("status", "active") != "active":
                continue
            self.add(fact, kind=item.get("type", "semantic"), embedding=item.get("embedding"),
                     importance=item.get("importance", 0.5), source=item.get("source", "Portable memory import"))
        return self.sync()

    def export(self) -> dict[str, Any]:
        return {"format": self.FORMAT, "memories": self._read()}

