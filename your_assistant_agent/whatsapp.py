from __future__ import annotations

from dataclasses import dataclass

import requests

from .db import Database
from .security import SecurityManager
from .text_utils import normalize_phone


class WhatsAppError(RuntimeError):
    pass


class WhatsAppNotConfigured(WhatsAppError):
    pass


@dataclass
class WhatsAppConfig:
    phone_number_id: str
    access_token: str
    api_version: str = "v24.0"


class WhatsAppBusinessClient:
    """Official WhatsApp Business Platform / Cloud API client.

    This client intentionally does not automate WhatsApp Web or native phone
    Broadcast Lists. Broadcast batching is handled by Your Assistant Agent and
    messages are sent individually through the official API.
    """

    def __init__(self, db: Database, security: SecurityManager):
        self.db = db
        self.security = security

    def config(self) -> WhatsAppConfig:
        phone_number_id = str(self.db.get_setting("wa_phone_number_id", "") or "").strip()
        api_version = str(self.db.get_setting("wa_api_version", "v24.0") or "v24.0").strip()
        access_token = self.security.get_secret("wa_access_token") or ""
        if not phone_number_id or not access_token:
            raise WhatsAppNotConfigured("WhatsApp Business Platform is not configured.")
        return WhatsAppConfig(phone_number_id, access_token, api_version)

    def is_configured(self) -> bool:
        try:
            self.config()
            return True
        except WhatsAppNotConfigured:
            return False

    def _post(self, payload: dict) -> dict:
        cfg = self.config()
        url = f"https://graph.facebook.com/{cfg.api_version}/{cfg.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {cfg.access_token}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
        except requests.RequestException as exc:
            raise WhatsAppError(f"Network error: {exc}") from exc

        try:
            data = response.json()
        except Exception:
            data = {"raw": response.text[:1000]}

        if response.status_code >= 400:
            message = ""
            if isinstance(data, dict):
                message = str((data.get("error") or {}).get("message") or data)
            raise WhatsAppError(f"WhatsApp API {response.status_code}: {message[:1000]}")
        return data

    def send_text(self, phone: str, text: str) -> dict:
        recipient = normalize_phone(phone)
        if not recipient or not text.strip():
            raise WhatsAppError("Recipient and message are required.")
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {"preview_url": True, "body": text.strip()},
        }
        return self._post(payload)

    def send_template(self, phone: str, template_name: str, language_code: str = "ar") -> dict:
        recipient = normalize_phone(phone)
        if not recipient or not template_name.strip():
            raise WhatsAppError("Recipient and template name are required.")
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "template",
            "template": {
                "name": template_name.strip(),
                "language": {"code": (language_code or "ar").strip()},
            },
        }
        return self._post(payload)
