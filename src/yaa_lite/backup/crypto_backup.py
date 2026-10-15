from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..config import config_dir, data_dir

MAGIC = b"YAA1"


def generate_recovery_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


def _key_bytes(key: str) -> bytes:
    raw = base64.urlsafe_b64decode(key.encode("ascii"))
    if len(raw) != 32:
        raise ValueError("Recovery key must decode to 32 bytes")
    return raw


def create_backup(destination: Path, recovery_key: str) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        zip_path = root / "payload.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for base, arc in [(data_dir(), "data"), (config_dir(), "config")]:
                if base.exists():
                    for p in base.rglob("*"):
                        if p.is_file() and not p.name.endswith("-wal") and not p.name.endswith("-shm"):
                            z.write(p, Path(arc) / p.relative_to(base))
        plain = zip_path.read_bytes()
    nonce = os.urandom(12)
    encrypted = AESGCM(_key_bytes(recovery_key)).encrypt(nonce, plain, MAGIC)
    destination.write_bytes(MAGIC + nonce + encrypted)
    return destination


def restore_backup(source: Path, recovery_key: str) -> None:
    blob = source.read_bytes()
    if not blob.startswith(MAGIC) or len(blob) < 17:
        raise ValueError("Not a valid Your Assistant Agent backup")
    nonce, encrypted = blob[4:16], blob[16:]
    plain = AESGCM(_key_bytes(recovery_key)).decrypt(nonce, encrypted, MAGIC)
    with tempfile.TemporaryDirectory() as td:
        zpath = Path(td) / "payload.zip"
        zpath.write_bytes(plain)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(Path(td) / "out")
        out = Path(td) / "out"
        for name, target in [("data", data_dir()), ("config", config_dir())]:
            src = out / name
            if src.exists():
                target.mkdir(parents=True, exist_ok=True)
                for p in src.rglob("*"):
                    if p.is_file():
                        dest = target / p.relative_to(src)
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(p, dest)
