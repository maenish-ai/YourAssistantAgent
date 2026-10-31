from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import secrets
import time
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from ..config import config_dir


class SecurityError(RuntimeError):
    pass


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data.encode("ascii"))


def _derive(secret: str, salt: bytes) -> bytes:
    if not secret:
        raise SecurityError("Empty secret")
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=260_000)
    return kdf.derive(secret.encode("utf-8"))


def _verifier(key: bytes) -> str:
    return hashlib.sha256(b"YAA-v2-verifier\0" + key).hexdigest()


def _wrap(master_key: bytes, wrapping_key: bytes, label: bytes) -> dict[str, str]:
    nonce = secrets.token_bytes(12)
    ct = AESGCM(wrapping_key).encrypt(nonce, master_key, label)
    return {"nonce": _b64(nonce), "ciphertext": _b64(ct)}


def _unwrap(payload: dict[str, str], wrapping_key: bytes, label: bytes) -> bytes:
    try:
        return AESGCM(wrapping_key).decrypt(_unb64(payload["nonce"]), _unb64(payload["ciphertext"]), label)
    except Exception as exc:
        raise SecurityError("Could not unlock encrypted key") from exc


def _boot_marker() -> str:
    if os.name == "nt":
        try:
            ms = int(ctypes.windll.kernel32.GetTickCount64())
            boot_epoch = int(time.time() - (ms / 1000.0))
            return f"win:{boot_epoch // 10}"
        except Exception:
            pass
    # Good enough fallback for non-Windows development/test environments.
    return f"session:{os.getuid() if hasattr(os, 'getuid') else 0}:{int(time.time()) // 86400}"


class SecurityManager:
    """Small local security layer for app unlock and encrypted secrets/backups.

    A random master key encrypts app secrets and backups. The master key is
    wrapped independently by the user's password and by a one-time recovery key.
    The raw password/recovery key is never written to disk.
    """

    STATE_FILE = "security.json"
    SESSION_FILE = "unlock-session.json"

    def __init__(self, root: Path | None = None):
        self.root = root or config_dir()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / self.STATE_FILE
        self.session_path = self.root / self.SESSION_FILE
        self._master_key: bytes | None = None

    @property
    def configured(self) -> bool:
        return self.path.exists()

    @property
    def unlocked(self) -> bool:
        return self._master_key is not None

    def _load(self) -> dict:
        if not self.path.exists():
            raise SecurityError("Security is not configured")
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise SecurityError("Security settings are damaged") from exc

    def _save(self, state: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def setup(self, password: str, mode: str = "every_launch") -> str:
        if mode not in {"every_launch", "windows_session", "none"}:
            raise SecurityError("Invalid password mode")
        if mode != "none" and len(password) < 4:
            raise SecurityError("Password must be at least 4 characters")

        recovery_key = "YAA-" + "-".join(secrets.token_hex(4).upper() for _ in range(6))
        master = secrets.token_bytes(32)
        recovery_salt = secrets.token_bytes(16)
        recovery_derived = _derive(recovery_key, recovery_salt)

        state: dict = {
            "version": 2,
            "mode": mode,
            "recovery_salt": _b64(recovery_salt),
            "recovery_verifier": _verifier(recovery_derived),
            "master_by_recovery": _wrap(master, recovery_derived, b"yaa-recovery"),
        }

        if mode == "none":
            # No app password: protect with a per-install random device secret.
            device_secret = secrets.token_urlsafe(48)
            device_path = self.root / ".device-key"
            device_path.write_text(device_secret, encoding="utf-8")
            try:
                os.chmod(device_path, 0o600)
            except Exception:
                pass
            device_salt = secrets.token_bytes(16)
            device_derived = _derive(device_secret, device_salt)
            state.update({
                "device_salt": _b64(device_salt),
                "device_verifier": _verifier(device_derived),
                "master_by_device": _wrap(master, device_derived, b"yaa-device"),
            })
        else:
            password_salt = secrets.token_bytes(16)
            password_derived = _derive(password, password_salt)
            state.update({
                "password_salt": _b64(password_salt),
                "password_verifier": _verifier(password_derived),
                "master_by_password": _wrap(master, password_derived, b"yaa-password"),
            })

        self._save(state)
        self._master_key = master
        self.mark_session_unlocked()
        return recovery_key

    def mode(self) -> str:
        if not self.configured:
            return "none"
        return str(self._load().get("mode") or "every_launch")

    def should_prompt(self) -> bool:
        if not self.configured:
            return False
        mode = self.mode()
        if mode == "none":
            self.unlock_without_password()
            return False
        if mode == "every_launch":
            return True
        if mode == "windows_session":
            try:
                marker = json.loads(self.session_path.read_text(encoding="utf-8"))
                if marker.get("boot") != _boot_marker():
                    return True
                self.unlock_from_session()
                return False
            except Exception:
                return True
        return True

    def _session_device_secret(self) -> str:
        path = self.root / ".session-device-key"
        if path.exists():
            return path.read_text(encoding="utf-8")
        secret = secrets.token_urlsafe(48)
        path.write_text(secret, encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
        return secret

    def mark_session_unlocked(self) -> None:
        if self._master_key is None:
            return
        try:
            boot = _boot_marker()
            salt = secrets.token_bytes(16)
            derived = _derive(self._session_device_secret() + boot, salt)
            wrapped = _wrap(self._master_key, derived, b"yaa-session")
            payload = {"boot": boot, "time": int(time.time()), "salt": _b64(salt), "wrapped": wrapped}
            self.session_path.write_text(json.dumps(payload), encoding="utf-8")
        except Exception:
            pass

    def unlock_from_session(self) -> bytes:
        payload = json.loads(self.session_path.read_text(encoding="utf-8"))
        boot = _boot_marker()
        if payload.get("boot") != boot:
            raise SecurityError("Session unlock expired")
        derived = _derive(self._session_device_secret() + boot, _unb64(payload["salt"]))
        master = _unwrap(payload["wrapped"], derived, b"yaa-session")
        self._master_key = master
        return master

    def unlock_with_password(self, password: str) -> bytes:
        state = self._load()
        if state.get("mode") == "none":
            return self.unlock_without_password()
        derived = _derive(password, _unb64(state["password_salt"]))
        if not secrets.compare_digest(_verifier(derived), str(state.get("password_verifier", ""))):
            raise SecurityError("Incorrect password")
        master = _unwrap(state["master_by_password"], derived, b"yaa-password")
        self._master_key = master
        self.mark_session_unlocked()
        return master

    def unlock_with_recovery(self, recovery_key: str) -> bytes:
        state = self._load()
        derived = _derive(recovery_key.strip(), _unb64(state["recovery_salt"]))
        if not secrets.compare_digest(_verifier(derived), str(state.get("recovery_verifier", ""))):
            raise SecurityError("Incorrect recovery key")
        master = _unwrap(state["master_by_recovery"], derived, b"yaa-recovery")
        self._master_key = master
        self.mark_session_unlocked()
        return master

    def unlock_without_password(self) -> bytes:
        state = self._load()
        if state.get("mode") != "none":
            raise SecurityError("Password is required")
        device_path = self.root / ".device-key"
        secret = device_path.read_text(encoding="utf-8")
        derived = _derive(secret, _unb64(state["device_salt"]))
        if not secrets.compare_digest(_verifier(derived), str(state.get("device_verifier", ""))):
            raise SecurityError("Device key mismatch")
        master = _unwrap(state["master_by_device"], derived, b"yaa-device")
        self._master_key = master
        return master

    def change_password(self, new_password: str, new_mode: str, recovery_key: str | None = None) -> None:
        if self._master_key is None:
            if recovery_key:
                self.unlock_with_recovery(recovery_key)
            else:
                raise SecurityError("Unlock the app before changing security")
        master = self._master_key
        assert master is not None
        state = self._load()
        state["mode"] = new_mode
        if new_mode == "none":
            device_secret = secrets.token_urlsafe(48)
            device_path = self.root / ".device-key"
            device_path.write_text(device_secret, encoding="utf-8")
            device_salt = secrets.token_bytes(16)
            derived = _derive(device_secret, device_salt)
            state["device_salt"] = _b64(device_salt)
            state["device_verifier"] = _verifier(derived)
            state["master_by_device"] = _wrap(master, derived, b"yaa-device")
            state.pop("password_salt", None)
            state.pop("password_verifier", None)
            state.pop("master_by_password", None)
        else:
            if len(new_password) < 4:
                raise SecurityError("Password must be at least 4 characters")
            salt = secrets.token_bytes(16)
            derived = _derive(new_password, salt)
            state["password_salt"] = _b64(salt)
            state["password_verifier"] = _verifier(derived)
            state["master_by_password"] = _wrap(master, derived, b"yaa-password")
            state.pop("device_salt", None)
            state.pop("device_verifier", None)
            state.pop("master_by_device", None)
        self._save(state)
        self.mark_session_unlocked()


    def portable_key_envelope(self) -> dict:
        """Return non-secret wrapping metadata suitable for an encrypted backup header.

        The returned values cannot decrypt the master key without the app
        password or recovery key, but they let a new device unwrap that same
        master key before the backed-up config has been restored.
        """
        state = self._load()
        allowed = {
            "version", "mode",
            "recovery_salt", "recovery_verifier", "master_by_recovery",
            "password_salt", "password_verifier", "master_by_password",
        }
        return {k: state[k] for k in allowed if k in state}

    @staticmethod
    def master_from_portable_envelope(envelope: dict, secret: str, use_recovery: bool = False) -> bytes:
        if use_recovery:
            salt_key, verifier_key, wrapped_key, label = "recovery_salt", "recovery_verifier", "master_by_recovery", b"yaa-recovery"
        else:
            salt_key, verifier_key, wrapped_key, label = "password_salt", "password_verifier", "master_by_password", b"yaa-password"
        if not envelope.get(salt_key) or not envelope.get(wrapped_key):
            raise SecurityError("This backup cannot be opened with that credential type")
        derived = _derive(secret.strip() if use_recovery else secret, _unb64(envelope[salt_key]))
        if not secrets.compare_digest(_verifier(derived), str(envelope.get(verifier_key, ""))):
            raise SecurityError("Incorrect backup password or recovery key")
        return _unwrap(envelope[wrapped_key], derived, label)

    def master_key(self) -> bytes:
        if self._master_key is None:
            raise SecurityError("App is locked")
        return self._master_key

    def encrypt(self, data: bytes, aad: bytes = b"yaa-data") -> bytes:
        key = self.master_key()
        nonce = secrets.token_bytes(12)
        return b"YAA2" + nonce + AESGCM(key).encrypt(nonce, data, aad)

    def decrypt(self, blob: bytes, aad: bytes = b"yaa-data") -> bytes:
        if not blob.startswith(b"YAA2") or len(blob) < 17:
            raise SecurityError("Unknown encrypted data format")
        key = self.master_key()
        nonce, ct = blob[4:16], blob[16:]
        try:
            return AESGCM(key).decrypt(nonce, ct, aad)
        except Exception as exc:
            raise SecurityError("Could not decrypt data") from exc
