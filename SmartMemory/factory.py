"""Create and cache the configured local or MongoDB ledger backend."""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path

from .ledger import MemoryLedger


@lru_cache(maxsize=512)
def _sqlite(path: str, user_id: str) -> MemoryLedger:
    return MemoryLedger(path, user_id=user_id)


@lru_cache(maxsize=512)
def _mongo(uri: str, database: str, collection: str, user_id: str):
    from .mongo_ledger import MongoMemoryLedger
    return MongoMemoryLedger(uri, user_id, database=database, collection=collection)


def open_ledger(user_id: str = "local", *, path: str | Path | None = None):
    """Open the selected backend, keeping one connection/store per user."""
    backend = os.getenv("NEXOR_VAULT_BACKEND", "sqlite").casefold()
    if backend == "mongodb":
        uri = os.getenv("NEXOR_VAULT_MONGO_URI") or os.getenv("MONGO_URI")
        if not uri:
            raise RuntimeError("Set NEXOR_VAULT_MONGO_URI to use the MongoDB ledger backend")
        return _mongo(uri, os.getenv("MEMORY_DATABASE", "Memory"),
                      os.getenv("NEXOR_VAULT_MONGO_COLLECTION", "memory_vault_ledger"), str(user_id))
    if backend != "sqlite":
        raise ValueError("NEXOR_VAULT_BACKEND must be sqlite or mongodb")
    if path is None:
        if os.getenv("NEXOR_VAULT_MULTIUSER", "false").casefold() == "true":
            root = Path(os.getenv("NEXOR_VAULT_ROOT", Path.home() / ".nexor" / "users"))
            import hashlib
            path = root / (hashlib.sha256(str(user_id).encode()).hexdigest() + ".sqlite3")
        else:
            path = os.getenv("NEXOR_VAULT_PATH", str(Path.home() / ".nexor" / "memory.sqlite3"))
    return _sqlite(str(path), str(user_id))
