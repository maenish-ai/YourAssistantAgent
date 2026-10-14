from __future__ import annotations

import base64
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .paths import app_data_dir, attachments_dir, db_path

MAGIC = b"YAA-BACKUP-V1\n"
SECRET_NAMES = (
    "github_token",
    "telegram_bot_token",
    "wa_access_token",
    "external_ai_api_key",
    "openai_api_key",
)


class BackupError(RuntimeError):
    pass


@dataclass
class BackupResult:
    path: Path
    created_at: str
    bytes_written: int


def generate_recovery_key() -> str:
    """Return a printable 256-bit recovery key suitable for cross-device restore."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


def _decode_key(value: str) -> bytes:
    try:
        key = base64.urlsafe_b64decode(str(value).encode("ascii"))
    except Exception as exc:
        raise BackupError("Recovery key is invalid.") from exc
    if len(key) != 32:
        raise BackupError("Recovery key must decode to 32 bytes.")
    return key


def encrypt_blob(data: bytes, recovery_key: str) -> bytes:
    key = _decode_key(recovery_key)
    nonce = os.urandom(12)
    cipher = AESGCM(key)
    return MAGIC + nonce + cipher.encrypt(nonce, data, MAGIC)


def decrypt_blob(data: bytes, recovery_key: str) -> bytes:
    if not data.startswith(MAGIC) or len(data) <= len(MAGIC) + 12:
        raise BackupError("This is not a valid Your Assistant Agent backup.")
    key = _decode_key(recovery_key)
    nonce = data[len(MAGIC):len(MAGIC) + 12]
    payload = data[len(MAGIC) + 12:]
    try:
        return AESGCM(key).decrypt(nonce, payload, MAGIC)
    except Exception as exc:
        raise BackupError("Could not decrypt backup. Check the Recovery Key.") from exc


class CloudBackupManager:
    """Encrypted local-first backups intended for a Google Drive synced folder.

    No paid cloud backend is required. The user chooses any folder synced by
    Google Drive for desktop (or another cloud provider). The app writes only an
    AES-GCM encrypted .yaa file there. The Facebook browser profile is excluded:
    sessions should be re-authenticated manually on a new PC.
    """

    def __init__(self, db, security):
        self.db = db
        self.security = security

    @property
    def folder(self) -> Path | None:
        value = str(self.db.get_setting("cloud_backup_folder", "") or "").strip()
        return Path(value) if value else None

    def set_folder(self, folder: str | Path) -> Path:
        path = Path(folder).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        self.db.set_setting("cloud_backup_folder", str(path))
        return path

    def ensure_recovery_key(self) -> str:
        key = self.security.get_secret("backup_recovery_key")
        if key:
            return key
        key = generate_recovery_key()
        self.security.set_secret("backup_recovery_key", key)
        return key

    def current_recovery_key(self) -> str:
        return self.security.get_secret("backup_recovery_key") or ""

    def import_recovery_key(self, key: str) -> None:
        _decode_key(key)
        self.security.set_secret("backup_recovery_key", key.strip())

    def _snapshot_db(self, destination: Path) -> None:
        source = sqlite3.connect(str(db_path()), timeout=30)
        dest = sqlite3.connect(str(destination), timeout=30)
        try:
            source.backup(dest)
        finally:
            dest.close()
            source.close()

    def _portable_secrets(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for name in SECRET_NAMES:
            try:
                value = self.security.get_secret(name)
            except Exception:
                value = ""
            if value:
                values[name] = value
        return values

    def _bundle(self) -> bytes:
        with tempfile.TemporaryDirectory(prefix="yaa-backup-") as td:
            tmp = Path(td)
            snapshot = tmp / "agent.db"
            self._snapshot_db(snapshot)
            meta = {
                "format": 1,
                "created_at": datetime.now().astimezone().replace(microsecond=0).isoformat(),
                "app": "Your Assistant Agent",
                "note": "Facebook browser cookies/profile intentionally excluded; reconnect Facebook on a new PC.",
            }
            (tmp / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            (tmp / "portable_secrets.json").write_text(
                json.dumps(self._portable_secrets(), ensure_ascii=False), encoding="utf-8"
            )
            archive = tmp / "bundle.zip"
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(snapshot, "agent.db")
                z.write(tmp / "metadata.json", "metadata.json")
                z.write(tmp / "portable_secrets.json", "portable_secrets.json")
                adir = attachments_dir()
                if adir.exists():
                    for p in adir.rglob("*"):
                        if p.is_file():
                            z.write(p, str(Path("attachments") / p.relative_to(adir)))
            return archive.read_bytes()

    def backup_now(self, folder: str | Path | None = None, keep_versions: int | None = None) -> BackupResult:
        target = self.set_folder(folder) if folder else self.folder
        if target is None:
            raise BackupError("Choose a Google Drive/cloud backup folder first.")
        target.mkdir(parents=True, exist_ok=True)
        key = self.ensure_recovery_key()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        encrypted = encrypt_blob(self._bundle(), key)
        versioned = target / f"YourAssistantAgent-{stamp}.yaa"
        latest = target / "YourAssistantAgent-latest.yaa"
        versioned.write_bytes(encrypted)
        latest.write_bytes(encrypted)
        self.db.set_setting("cloud_backup_last_at", datetime.now().astimezone().replace(microsecond=0).isoformat())
        self.db.set_setting("cloud_backup_last_file", str(versioned))
        self.db.audit("INFO", "cloud_backup_done", str(versioned))
        self.prune_versions(target, int(keep_versions or self.db.get_setting("cloud_backup_keep_versions", 7) or 7))
        return BackupResult(versioned, self.db.get_setting("cloud_backup_last_at", ""), len(encrypted))

    @staticmethod
    def prune_versions(folder: Path, keep: int = 7) -> None:
        keep = max(1, min(int(keep), 50))
        files = sorted(folder.glob("YourAssistantAgent-????????-??????.yaa"), key=lambda p: p.name, reverse=True)
        for old in files[keep:]:
            try:
                old.unlink()
            except OSError:
                pass

    def restore(self, backup_file: str | Path, recovery_key: str) -> dict:
        path = Path(backup_file)
        if not path.exists():
            raise BackupError("Backup file does not exist.")
        plain = decrypt_blob(path.read_bytes(), recovery_key)
        with tempfile.TemporaryDirectory(prefix="yaa-restore-") as td:
            tmp = Path(td)
            archive = tmp / "bundle.zip"
            archive.write_bytes(plain)
            with zipfile.ZipFile(archive, "r") as z:
                # protect against path traversal
                for info in z.infolist():
                    candidate = (tmp / "unpacked" / info.filename).resolve()
                    base = (tmp / "unpacked").resolve()
                    if base not in candidate.parents and candidate != base:
                        raise BackupError("Backup contains an unsafe path.")
                z.extractall(tmp / "unpacked")
            unpacked = tmp / "unpacked"
            restored_db = unpacked / "agent.db"
            if not restored_db.exists():
                raise BackupError("Backup is missing agent.db.")
            # There are no persistent sqlite connections in Database.conn(), so
            # replacing the file between operations is safe. Keep a local rescue.
            current = db_path()
            rescue = app_data_dir() / "agent.before_restore.db"
            if current.exists():
                shutil.copy2(current, rescue)
            shutil.copy2(restored_db, current)

            adir = attachments_dir()
            restored_attachments = unpacked / "attachments"
            if restored_attachments.exists():
                if adir.exists():
                    shutil.rmtree(adir, ignore_errors=True)
                shutil.copytree(restored_attachments, adir, dirs_exist_ok=True)

            self.db.init()
            # On a new PC the synced Drive folder may have a different absolute
            # path, so adopt the folder the user restored from.
            self.db.set_setting("cloud_backup_folder", str(path.parent.resolve()))
            secrets_path = unpacked / "portable_secrets.json"
            if secrets_path.exists():
                try:
                    secrets = json.loads(secrets_path.read_text(encoding="utf-8"))
                except Exception:
                    secrets = {}
                if isinstance(secrets, dict):
                    for name, value in secrets.items():
                        if name in SECRET_NAMES and isinstance(value, str) and value:
                            self.security.set_secret(name, value)
            # Store the supplied recovery key using this machine's DPAPI.
            self.import_recovery_key(recovery_key)
            self.db.audit("SECURITY", "cloud_backup_restored", str(path))
            meta = {}
            meta_path = unpacked / "metadata.json"
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except Exception:
                    meta = {}
            return meta
