from __future__ import annotations

import base64
import hashlib
import http.server
import json
import secrets
import socketserver
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

import requests

from ..config import Settings, data_dir
from ..security.manager import SecurityManager, SecurityError

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DRIVE_UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
DRIVE_FILES = "https://www.googleapis.com/drive/v3/files"
SCOPES = "openid email https://www.googleapis.com/auth/drive.appdata"


class DriveAuthError(RuntimeError):
    pass


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    result: dict[str, str] = {}
    event = threading.Event()

    def do_GET(self):  # noqa: N802
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        type(self).result = {k: v[0] for k, v in q.items() if v}
        body = b"<html><body><h2>Your Assistant Agent</h2><p>Google Drive connected. You can close this tab.</p></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        type(self).event.set()

    def log_message(self, fmt, *args):
        return


class GoogleDriveClient:
    """Minimal Google Drive OAuth/REST client using appDataFolder.

    A real Google OAuth Desktop client ID is required. The application never
    invents or embeds a fake credential; the ID can be provided in Settings or
    at packaging time via YAA_GOOGLE_DRIVE_CLIENT_ID.
    """

    def __init__(self, settings: Settings, security: SecurityManager):
        self.settings = settings
        self.security = security
        self.token_file = data_dir() / "backups" / "google-drive-token.bin"
        self.token_file.parent.mkdir(parents=True, exist_ok=True)

    def _client_id(self) -> str:
        import os
        return (self.settings.google_drive_client_id or os.getenv("YAA_GOOGLE_DRIVE_CLIENT_ID", "")).strip()

    def _client_secret(self) -> str:
        import os
        return (self.settings.google_drive_client_secret or os.getenv("YAA_GOOGLE_DRIVE_CLIENT_SECRET", "")).strip()

    def _save_token(self, token: dict) -> None:
        raw = json.dumps(token, ensure_ascii=False).encode("utf-8")
        self.token_file.write_bytes(self.security.encrypt(raw, b"yaa-google-drive-token"))

    def _load_token(self) -> dict:
        if not self.token_file.exists():
            return {}
        try:
            raw = self.security.decrypt(self.token_file.read_bytes(), b"yaa-google-drive-token")
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def has_token(self) -> bool:
        return bool(self._load_token().get("refresh_token") or self._load_token().get("access_token")) if self.security.unlocked else False

    def disconnect(self) -> None:
        try:
            self.token_file.unlink(missing_ok=True)
        except Exception:
            pass

    def authorize(self, timeout: int = 180) -> str:
        client_id = self._client_id()
        if not client_id:
            raise DriveAuthError("Google Drive OAuth client ID is not configured")

        verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).decode("ascii").rstrip("=")
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
        state = secrets.token_urlsafe(24)

        _CallbackHandler.result = {}
        _CallbackHandler.event = threading.Event()
        with socketserver.TCPServer(("127.0.0.1", 0), _CallbackHandler) as server:
            port = int(server.server_address[1])
            redirect = f"http://127.0.0.1:{port}/oauth2callback"
            params = {
                "client_id": client_id,
                "redirect_uri": redirect,
                "response_type": "code",
                "scope": SCOPES,
                "access_type": "offline",
                "prompt": "consent",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": state,
            }
            webbrowser.open(AUTH_URL + "?" + urllib.parse.urlencode(params))
            thread = threading.Thread(target=server.handle_request, daemon=True)
            thread.start()
            if not _CallbackHandler.event.wait(timeout):
                raise DriveAuthError("Google Drive authorization timed out")

        result = _CallbackHandler.result
        if result.get("state") != state or not result.get("code"):
            raise DriveAuthError(result.get("error") or "Google Drive authorization failed")

        payload = {
            "client_id": client_id,
            "code": result["code"],
            "code_verifier": verifier,
            "redirect_uri": redirect,
            "grant_type": "authorization_code",
        }
        secret = self._client_secret()
        if secret:
            payload["client_secret"] = secret
        r = requests.post(TOKEN_URL, data=payload, timeout=30)
        if not r.ok:
            raise DriveAuthError(f"Token exchange failed ({r.status_code})")
        token = r.json()
        token["obtained_at"] = int(time.time())
        self._save_token(token)
        return self.account_email()

    def _access_token(self) -> str:
        token = self._load_token()
        access = str(token.get("access_token") or "")
        expires = int(token.get("expires_in") or 0)
        obtained = int(token.get("obtained_at") or 0)
        if access and (not expires or time.time() < obtained + expires - 60):
            return access
        refresh = str(token.get("refresh_token") or "")
        if not refresh:
            raise DriveAuthError("Google Drive is not connected")
        payload = {
            "client_id": self._client_id(),
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        }
        secret = self._client_secret()
        if secret:
            payload["client_secret"] = secret
        r = requests.post(TOKEN_URL, data=payload, timeout=30)
        if not r.ok:
            raise DriveAuthError("Could not refresh Google Drive access")
        updated = r.json()
        token.update(updated)
        token["obtained_at"] = int(time.time())
        self._save_token(token)
        return str(token.get("access_token") or "")

    def account_email(self) -> str:
        token = self._load_token() if self.security.unlocked else {}
        id_token = str(token.get("id_token") or "")
        if not id_token or id_token.count(".") < 2:
            return ""
        try:
            payload = id_token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
            return str(data.get("email") or "")
        except Exception:
            return ""

    def upload_backup(self, path: Path) -> str:
        token = self._access_token()
        boundary = "yaa" + secrets.token_hex(12)
        metadata = json.dumps({"name": path.name, "parents": ["appDataFolder"]}).encode("utf-8")
        content = path.read_bytes()
        body = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode()
            + metadata
            + f"\r\n--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n".encode()
            + content
            + f"\r\n--{boundary}--\r\n".encode()
        )
        r = requests.post(
            DRIVE_UPLOAD,
            params={"uploadType": "multipart", "fields": "id,name,createdTime"},
            headers={"Authorization": f"Bearer {token}", "Content-Type": f"multipart/related; boundary={boundary}"},
            data=body,
            timeout=120,
        )
        if not r.ok:
            raise DriveAuthError(f"Google Drive upload failed ({r.status_code})")
        return str(r.json().get("id") or "")

    def list_backups(self, limit: int = 50) -> list[dict]:
        token = self._access_token()
        r = requests.get(
            DRIVE_FILES,
            params={
                "spaces": "appDataFolder",
                "q": "name contains 'YourAssistantAgent-' and trashed=false",
                "pageSize": max(1, min(int(limit), 100)),
                "orderBy": "createdTime desc",
                "fields": "files(id,name,size,createdTime,modifiedTime)",
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if not r.ok:
            raise DriveAuthError(f"Could not list backups ({r.status_code})")
        return list(r.json().get("files") or [])

    def download_backup(self, file_id: str, destination: Path) -> Path:
        token = self._access_token()
        r = requests.get(
            f"{DRIVE_FILES}/{urllib.parse.quote(file_id)}",
            params={"alt": "media"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=120,
        )
        if not r.ok:
            raise DriveAuthError(f"Google Drive download failed ({r.status_code})")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(r.content)
        return destination
