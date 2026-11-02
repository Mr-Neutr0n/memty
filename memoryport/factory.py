"""Create and cache the configured local or MongoDB ledger backend."""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path

from .ledger import MemoryLedger


def default_vault_path() -> Path:
    """Use Memty's data folder, reusing older vaults when they already exist."""
    configured = (os.getenv("MEMTY_MEMORY_PATH") or os.getenv("MEMTY_VAULT_PATH")
                  or os.getenv("NEXORAI_MEMORY_PATH") or os.getenv("NEXOR_VAULT_PATH"))
    if configured:
        return Path(configured).expanduser()
    home = Path.home()
    current = home / ".memty" / "memory.sqlite3"
    previous = home / ".nexorai" / "memory.sqlite3"
    legacy = home / ".nexor" / "memory.sqlite3"
    if current.exists():
        return current
    if previous.exists():
        return previous
    if legacy.exists():
        return legacy
    return current


@lru_cache(maxsize=512)
def _sqlite(path: str, user_id: str) -> MemoryLedger:
    return MemoryLedger(path, user_id=user_id)


@lru_cache(maxsize=512)
def _mongo(uri: str, database: str, collection: str, user_id: str):
    from .mongo_ledger import MongoMemoryLedger
    return MongoMemoryLedger(uri, user_id, database=database, collection=collection)


def open_ledger(user_id: str = "local", *, path: str | Path | None = None):
    """Open the selected backend, keeping one connection/store per user."""
    backend = os.getenv("MEMTY_VAULT_BACKEND", os.getenv("NEXOR_VAULT_BACKEND", "sqlite")).casefold()
    if backend == "mongodb":
        uri = os.getenv("MEMTY_VAULT_MONGO_URI") or os.getenv("NEXOR_VAULT_MONGO_URI") or os.getenv("MONGO_URI")
        if not uri:
            raise RuntimeError("Set MEMTY_VAULT_MONGO_URI to use the MongoDB ledger backend")
        return _mongo(uri, os.getenv("MEMORY_DATABASE", "Memory"),
                      os.getenv("MEMTY_VAULT_MONGO_COLLECTION", os.getenv("NEXOR_VAULT_MONGO_COLLECTION", "memory_vault_ledger")), str(user_id))
    if backend != "sqlite":
        raise ValueError("MEMTY_VAULT_BACKEND must be sqlite or mongodb")
    if path is None:
        if os.getenv("MEMTY_VAULT_MULTIUSER", os.getenv("NEXOR_VAULT_MULTIUSER", "false")).casefold() == "true":
            root = Path(os.getenv("MEMTY_VAULT_ROOT", Path.home() / ".memty" / "users"))
            import hashlib
            path = root / (hashlib.sha256(str(user_id).encode()).hexdigest() + ".sqlite3")
        else:
            path = default_vault_path()
    return _sqlite(str(path), str(user_id))

