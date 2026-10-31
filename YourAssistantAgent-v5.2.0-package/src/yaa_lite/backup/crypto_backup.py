from __future__ import annotations

import base64
import io
import json
import os
import shutil
import struct
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..config import config_dir, data_dir
from ..security.manager import SecurityManager

MAGIC = b"YAA3"
LEGACY_MAGIC = b"YAA2"


def generate_recovery_key() -> str:
    """Legacy helper kept for older callers/tests."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


def _zip_payload(include_attachments: bool = True, include_facebook_credentials: bool = False) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        manifest = {
            "format": 3,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "include_attachments": bool(include_attachments),
        }
        z.writestr("backup_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for base, arc in [(data_dir(), "data"), (config_dir(), "config")]:
            if not base.exists():
                continue
            for p in base.rglob("*"):
                if not p.is_file() or p.name.endswith(("-wal", "-shm")):
                    continue
                rel = p.relative_to(base)
                if arc == "data" and rel.parts and rel.parts[0] == "backups":
                    continue
                if arc == "data" and rel.parts[:2] in {("mobile", "inbox"), ("mobile", "relay")}:
                    # Partial uploads and replay-cache records are transient,
                    # not user documents to include in backup/sync payloads.
                    continue
                if not include_facebook_credentials and arc == "data" and rel.parts and rel.parts[0] == "facebook_profile":
                    continue
                if not include_attachments and "attachments" in rel.parts:
                    continue
                if p.name == "unlock-session.json":
                    continue
                z.write(p, Path(arc) / rel)
    return buf.getvalue()


def _write_container(destination: Path, key: bytes, plain: bytes, envelope: dict | None = None) -> Path:
    if len(key) != 32:
        raise ValueError("Backup key must be 32 bytes")
    destination.parent.mkdir(parents=True, exist_ok=True)
    header = json.dumps({"format": 3, "key_envelope": envelope or {}}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    nonce = os.urandom(12)
    encrypted = AESGCM(key).encrypt(nonce, plain, MAGIC + header)
    destination.write_bytes(MAGIC + struct.pack(">I", len(header)) + header + nonce + encrypted)
    return destination


def _read_container(source: Path) -> tuple[dict, bytes, bytes]:
    blob = source.read_bytes()
    if blob.startswith(MAGIC):
        if len(blob) < 4 + 4 + 12 + 16:
            raise ValueError("Damaged Your Assistant Agent backup")
        hlen = struct.unpack(">I", blob[4:8])[0]
        if hlen <= 0 or hlen > 1_000_000 or len(blob) < 8 + hlen + 12 + 16:
            raise ValueError("Invalid backup header")
        header_raw = blob[8:8 + hlen]
        header = json.loads(header_raw.decode("utf-8"))
        nonce = blob[8 + hlen:20 + hlen]
        encrypted = blob[20 + hlen:]
        return header, nonce, encrypted
    if blob.startswith(LEGACY_MAGIC) and len(blob) >= 17:
        return {"format": 2, "key_envelope": {}}, blob[4:16], blob[16:]
    raise ValueError("Not a valid Your Assistant Agent backup")


def backup_header(source: Path) -> dict:
    header, _, _ = _read_container(source)
    return header


def create_backup_with_key(destination: Path, key: bytes, include_attachments: bool = True, envelope: dict | None = None, include_facebook_credentials: bool = False) -> Path:
    return _write_container(destination, key, _zip_payload(include_attachments=include_attachments, include_facebook_credentials=include_facebook_credentials), envelope=envelope)


def create_backup_with_security(destination: Path, security: SecurityManager, include_attachments: bool = True, include_facebook_credentials: bool = False) -> Path:
    return create_backup_with_key(destination, security.master_key(), include_attachments, security.portable_key_envelope(), include_facebook_credentials=include_facebook_credentials)


def _decrypt_plain(source: Path, key: bytes) -> bytes:
    header, nonce, encrypted = _read_container(source)
    if int(header.get("format") or 0) >= 3:
        header_raw = json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        aad = MAGIC + header_raw
    else:
        aad = LEGACY_MAGIC
    return AESGCM(key).decrypt(nonce, encrypted, aad)


def _restore_plain(plain: bytes) -> None:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out"; out.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(plain)) as z:
            # Refuse path traversal from corrupted/untrusted backup files.
            root = out.resolve()
            for info in z.infolist():
                target = (out / info.filename).resolve()
                if root not in target.parents and target != root:
                    raise ValueError("Unsafe path in backup")
            z.extractall(out)
        for name, target in [("data", data_dir()), ("config", config_dir())]:
            src = out / name
            if not src.exists():
                continue
            target.mkdir(parents=True, exist_ok=True)
            for p in src.rglob("*"):
                if p.is_file():
                    dest = target / p.relative_to(src)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, dest)


def restore_backup_with_key(source: Path, key: bytes) -> None:
    _restore_plain(_decrypt_plain(source, key))


def restore_backup_with_secret(source: Path, secret: str, use_recovery: bool = False) -> None:
    header, _, _ = _read_container(source)
    envelope = header.get("key_envelope") if isinstance(header, dict) else {}
    if not isinstance(envelope, dict) or not envelope:
        raise ValueError("This backup does not contain portable recovery metadata")
    key = SecurityManager.master_from_portable_envelope(envelope, secret, use_recovery=use_recovery)
    _restore_plain(_decrypt_plain(source, key))


# Backward-compatible helpers for callers passing a raw 32-byte base64 key.
def _legacy_key_bytes(key: str) -> bytes:
    raw = base64.urlsafe_b64decode(key.encode("ascii"))
    if len(raw) != 32:
        raise ValueError("Recovery key must decode to 32 bytes")
    return raw


def create_backup(destination: Path, recovery_key: str) -> Path:
    return create_backup_with_key(destination, _legacy_key_bytes(recovery_key))


def restore_backup(source: Path, recovery_key: str) -> None:
    restore_backup_with_key(source, _legacy_key_bytes(recovery_key))
