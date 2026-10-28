"""Single-file .nxvault export/import helpers.

Archives are encrypted by default. The optional ``crypto`` extra supplies
AES-256-GCM and scrypt; unencrypted export requires an explicit opt-in.
"""

from __future__ import annotations

import hashlib
import io
import json
import secrets
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ledger import MemoryLedger, SCHEMA_VERSION


MAGIC = b"NXVAULT1"
_AAD = b"nexor-nxvault-v1"


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _crypto():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    except ImportError as error:
        raise RuntimeError("Encrypted vaults require: pip install 'nexorai-smart-auto[crypto]'") from error
    return AESGCM, Scrypt


def _derive(passphrase: str, salt: bytes) -> bytes:
    AESGCM, Scrypt = _crypto()
    del AESGCM
    if not isinstance(passphrase, str) or len(passphrase) < 10:
        raise ValueError("vault passphrase must contain at least 10 characters")
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode("utf-8"))


def _archive(ledger: MemoryLedger) -> bytes:
    payload = ledger.export_payload()
    event_lines = b"".join(_json_bytes(event) + b"\n" for event in payload["events"])
    policy_lines = b"".join(_json_bytes({"id": event["id"], "allowed_providers": event["allowed_providers"],
                                         "blocked_providers": event["blocked_providers"],
                                         "sensitivity_tier": event["sensitivity_tier"],
                                         "ephemeral_redaction": event["ephemeral_redaction"]}) + b"\n"
                            for event in payload["events"])
    manifest = {"format": payload["format"], "schema_version": SCHEMA_VERSION,
                "exported_at": payload["exported_at"], "user_id": payload["user_id"],
                "files": {"ledger.jsonl": hashlib.sha256(event_lines).hexdigest(),
                          "policies.jsonl": hashlib.sha256(policy_lines).hexdigest()},
                "pending_proposals": payload["proposals"]}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, data in (("manifest.json", _json_bytes(manifest)),
                           ("ledger.jsonl", event_lines), ("policies.jsonl", policy_lines)):
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, data)
    return output.getvalue()


def export_nxvault(ledger: MemoryLedger, path: str | Path, *, passphrase: str | None = None,
                   allow_plaintext: bool = False) -> Path:
    """Write an encrypted .nxvault. Plaintext requires explicit opt-in."""
    destination = Path(path)
    if destination.suffix.lower() != ".nxvault":
        raise ValueError("vault files must use the .nxvault extension")
    if passphrase is None:
        if not allow_plaintext:
            raise ValueError("encrypted export is the default; provide a passphrase or explicitly set allow_plaintext=True")
        data = _archive(ledger)
    else:
        data = encode_nxvault(ledger, passphrase=passphrase)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + ".tmp")
    try:
        temp.write_bytes(data)
        temp.replace(destination)
    finally:
        if temp.exists():
            temp.unlink()
    return destination


def encode_nxvault(ledger: MemoryLedger, *, passphrase: str | None) -> bytes:
    """Return an encrypted archive for in-memory HTTP transfer."""
    if passphrase is None:
        raise ValueError("encrypted export requires a passphrase")
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    AESGCM, _ = _crypto()
    key = _derive(passphrase, salt)
    return MAGIC + salt + nonce + AESGCM(key).encrypt(nonce, _archive(ledger), _AAD)


def _unpack(data: bytes, passphrase: str | None) -> dict[str, Any]:
    if data.startswith(MAGIC):
        if passphrase is None:
            raise ValueError("this vault is encrypted; supply its passphrase")
        if len(data) < len(MAGIC) + 28:
            raise ValueError("invalid encrypted vault")
        start = len(MAGIC)
        salt, nonce, encrypted = data[start:start + 16], data[start + 16:start + 28], data[start + 28:]
        AESGCM, _ = _crypto()
        try:
            data = AESGCM(_derive(passphrase, salt)).decrypt(nonce, encrypted, _AAD)
        except Exception as error:
            raise ValueError("vault could not be decrypted; check the passphrase or file integrity") from error
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
            allowed = {"manifest.json", "ledger.jsonl", "policies.jsonl"}
            if set(archive.namelist()) != allowed:
                raise ValueError("vault contains unexpected files")
            manifest = json.loads(archive.read("manifest.json"))
            events_bytes = archive.read("ledger.jsonl")
            policies_bytes = archive.read("policies.jsonl")
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as error:
        raise ValueError("invalid .nxvault file") from error
    if manifest.get("format") != MemoryLedger.FORMAT or int(manifest.get("schema_version", 0)) > SCHEMA_VERSION:
        raise ValueError("unsupported or newer vault format")
    files = manifest.get("files", {})
    if hashlib.sha256(events_bytes).hexdigest() != files.get("ledger.jsonl") or hashlib.sha256(policies_bytes).hexdigest() != files.get("policies.jsonl"):
        raise ValueError("vault integrity check failed")
    try:
        events = [json.loads(line) for line in events_bytes.splitlines() if line.strip()]
    except json.JSONDecodeError as error:
        raise ValueError("invalid ledger data in vault") from error
    return {"format": manifest["format"], "schema_version": manifest["schema_version"],
            "user_id": manifest.get("user_id", ""), "exported_at": manifest.get("exported_at"),
            "events": events, "proposals": manifest.get("pending_proposals", [])}


def import_nxvault(ledger: MemoryLedger, path: str | Path, *, passphrase: str | None = None,
                   merge: bool = True) -> int:
    """Verify and import vault history into this user's ledger."""
    payload = _unpack(Path(path).read_bytes(), passphrase)
    return ledger.import_payload(payload, merge=merge)

