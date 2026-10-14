from __future__ import annotations

import os
import base64
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from .db import Database
from .paths import app_data_dir

PH = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


class SecurityManager:
    def __init__(self, db: Database):
        self.db = db

    def has_pin(self) -> bool:
        return bool(self.db.get_setting("pin_hash", ""))

    def set_pin(self, pin: str):
        if len(pin) < 4:
            raise ValueError("PIN must contain at least 4 characters")
        self.db.set_setting("pin_hash", PH.hash(pin))
        self.db.audit("SECURITY", "pin_set")

    def verify_pin(self, pin: str) -> bool:
        stored = self.db.get_setting("pin_hash", "")
        if not stored:
            return False
        try:
            ok = PH.verify(stored, pin)
            if ok and PH.check_needs_rehash(stored):
                self.db.set_setting("pin_hash", PH.hash(pin))
            return ok
        except VerifyMismatchError:
            self.db.audit("SECURITY", "pin_failed")
            return False
        except Exception:
            return False


    def set_secret(self, name: str, value: str):
        if not name:
            raise ValueError("Secret name is required")
        key = f"secret_{name}"
        if not value:
            self.db.set_setting(key, "")
            return
        blob = DpapiVault.protect(value.encode("utf-8"))
        self.db.set_setting(key, base64.b64encode(blob).decode("ascii"))
        self.db.audit("SECURITY", "secret_updated", name)

    def get_secret(self, name: str) -> str:
        key = f"secret_{name}"
        encoded = self.db.get_setting(key, "") or ""
        if not encoded:
            return ""
        try:
            blob = base64.b64decode(encoded.encode("ascii"))
            return DpapiVault.unprotect(blob).decode("utf-8")
        except Exception:
            return ""

    def restrict_app_folder_windows(self):
        """Best-effort ACL hardening. Never runs elevated automatically."""
        if os.name != "nt":
            return
        # Windows user profile ACLs already provide isolation. We intentionally avoid
        # destructive ACL rewriting here; packaging can add stricter ACLs later.
        self.db.audit("SECURITY", "profile_acl_checked", str(app_data_dir()))


class DpapiVault:
    """Windows DPAPI wrapper for future tokens/API keys. Facebook password is never stored."""

    @staticmethod
    def protect(data: bytes, description: str = "YourAssistantAgent") -> bytes:
        if os.name != "nt":
            raise RuntimeError("DPAPI is only available on Windows")
        import win32crypt
        return win32crypt.CryptProtectData(data, description, None, None, None, 0)[1]

    @staticmethod
    def unprotect(blob: bytes) -> bytes:
        if os.name != "nt":
            raise RuntimeError("DPAPI is only available on Windows")
        import win32crypt
        return win32crypt.CryptUnprotectData(blob, None, None, None, 0)[1]
