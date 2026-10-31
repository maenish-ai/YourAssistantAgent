from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..config import Settings, data_dir
from ..security.manager import SecurityManager
from .crypto_backup import create_backup_with_security, restore_backup_with_key, restore_backup_with_secret
from .google_drive import GoogleDriveClient, DriveAuthError


@dataclass
class BackupStatus:
    connected: bool = False
    account: str = ""
    last_backup: str = ""
    last_sync: str = ""
    detail: str = ""


class BackupService:
    """Encrypted local snapshot + optional Google Drive appDataFolder sync."""

    def __init__(self, settings: Settings, security: SecurityManager, activity: Callable[[str, str], None] | None = None):
        self.settings = settings
        self.security = security
        self.activity = activity or (lambda *_: None)
        self.root = data_dir() / "backups"
        self.root.mkdir(parents=True, exist_ok=True)
        self.meta_path = self.root / "status.json"
        self._lock = threading.RLock()
        self.drive = GoogleDriveClient(settings, security)

    def update_settings(self, settings: Settings) -> None:
        self.settings = settings
        self.drive.settings = settings

    def _meta(self) -> dict:
        try:
            return json.loads(self.meta_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_meta(self, **updates) -> None:
        meta = self._meta()
        meta.update(updates)
        self.meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def create_local_backup(self, include_attachments: bool | None = None) -> Path:
        with self._lock:
            include = self.settings.drive_sync_attachments if include_attachments is None else bool(include_attachments)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            dest = self.root / f"YourAssistantAgent-{stamp}.yaa-backup"
            create_backup_with_security(dest, self.security, include_attachments=include, include_facebook_credentials=self.settings.sync_facebook_credentials)
            self._save_meta(last_backup=datetime.now().isoformat(timespec="seconds"), last_backup_path=str(dest))
            self.activity("backup_created", str(dest))
            return dest

    def restore_local_backup(self, source: Path) -> None:
        with self._lock:
            restore_backup_with_key(source, self.security.master_key())
            self.activity("backup_restored", str(source))

    def list_local_backups(self) -> list[Path]:
        return sorted(self.root.glob("*.yaa-backup"), key=lambda p: p.stat().st_mtime, reverse=True)

    def connect_drive(self) -> str:
        account = self.drive.authorize()
        self._save_meta(drive_account=account)
        self.activity("drive_connected", account)
        return account

    def disconnect_drive(self) -> None:
        self.drive.disconnect()
        self._save_meta(drive_account="", last_sync="")
        self.activity("drive_disconnected", "")

    def sync_now(self) -> str:
        local = self.create_local_backup()
        remote_id = self.drive.upload_backup(local)
        now = datetime.now().isoformat(timespec="seconds")
        self._save_meta(last_sync=now, remote_id=remote_id)
        self.activity("drive_sync", f"{local.name}; id={remote_id}")
        return remote_id


    def list_drive_backups(self, limit: int = 50) -> list[dict]:
        return self.drive.list_backups(limit=limit)

    def restore_drive_backup(self, file_id: str, *, secret: str | None = None, use_recovery: bool = False) -> Path:
        """Download and restore a Drive backup.

        On the same unlocked device ``secret`` may be omitted. On a new device,
        pass the original app password or Recovery Key; the portable backup
        envelope unwraps the original master key before restoring its config.
        """
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        temp = self.root / f"drive-restore-{stamp}.yaa-backup"
        self.drive.download_backup(file_id, temp)
        try:
            if secret is None:
                restore_backup_with_key(temp, self.security.master_key())
            else:
                restore_backup_with_secret(temp, secret, use_recovery=use_recovery)
            self.activity("backup_restored", f"drive:{file_id}")
            return temp
        except Exception:
            temp.unlink(missing_ok=True)
            raise

    def status(self) -> BackupStatus:
        meta = self._meta()
        connected = self.drive.has_token()
        return BackupStatus(
            connected=connected,
            account=str(meta.get("drive_account") or self.drive.account_email() or ""),
            last_backup=str(meta.get("last_backup") or ""),
            last_sync=str(meta.get("last_sync") or ""),
            detail="connected" if connected else "not_connected",
        )
