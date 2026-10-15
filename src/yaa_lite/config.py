from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from platformdirs import user_config_dir, user_data_dir

APP_NAME = "YourAssistantAgent"
APP_AUTHOR = "YourAssistantAgent"


def config_dir() -> Path:
    p = Path(user_config_dir(APP_NAME, APP_AUTHOR))
    p.mkdir(parents=True, exist_ok=True)
    return p


def data_dir() -> Path:
    p = Path(user_data_dir(APP_NAME, APP_AUTHOR))
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class Settings:
    # v2.0: one assistant only. Older values are migrated to Hammer.
    selected_agent: str = "hammer"
    remember_agent: bool = True
    smart_agent_framework: str = "hammer2.1-primary-agent"

    # First run / UI. No bilingual runtime UI: Arabic OR English.
    first_run_complete: bool = False
    interface_language: str = "ar"
    appearance: str = "system"  # system | light | dark
    startup_page: str = "home"  # home | chat | last
    last_page: str = "home"
    close_behavior: str = "tray"  # tray | exit | ask
    start_with_windows: str = "tray"  # off | tray | window

    # Hammer is the only reasoning/chat model.
    smart_agent_enabled: bool = True
    ai_timeout_seconds: int = 90
    context_tokens: int = 2048
    max_response_tokens: int = 160
    threads: int = 2
    hammer_retry_count: int = 2  # retries after the initial attempt
    hammer_idle_minutes: int = 15  # 0 = never unload automatically
    performance_mode: str = "balanced"  # eco | balanced | performance
    reply_language: str = "message"  # message | interface | ar | en
    arabic_dialect: str = "jordanian"
    assistant_name: str = "Assistant"
    personality_style: str = "friendly"
    personality_prompt: str = ""
    suggestion_level: str = "medium"

    # Security / approvals.
    password_mode: str = "every_launch"  # every_launch | windows_session | none
    approval_timeout_minutes: int = 30
    confirmation_policy: str = "always"  # always | threshold | auto
    confirmation_group_threshold: int = 10
    confirm_external_actions: bool = True

    # Facebook / browser.
    default_source_page: str = ""
    facebook_auto_check: bool = True
    facebook_browser_choice: str = "auto"  # auto/default/edge/chrome/firefox/custom
    facebook_browser_custom_path: str = ""
    facebook_browser_mode: str = "extension_first"  # extension_first | managed_profile
    facebook_interval_min_seconds: int = 50
    facebook_interval_max_seconds: int = 90
    facebook_hourly_limit: int = 30
    facebook_daily_limit: int = 120
    facebook_no_repeat_days: int = 14
    facebook_pending_check_minutes: int = 60

    # Backup / Google Drive.
    auto_backup: bool = True
    drive_sync_enabled: bool = False
    drive_sync_interval_minutes: int = 60
    drive_sync_attachments: bool = True
    drive_backup_folder: str = "appDataFolder"
    google_drive_client_id: str = ""
    google_drive_client_secret: str = ""
    sync_facebook_credentials: bool = False
    sync_telegram_credentials: bool = False
    sync_github_credentials: bool = False

    # Notifications / remote control.
    notify_in_app: bool = True
    notify_windows: bool = True
    notify_telegram: bool = False
    telegram_enabled: bool = False
    github_enabled: bool = False

    # Voice. Runtime is optional/lazy so the 4 GB machine stays light.
    voice_enabled: bool = False
    voice_backend: str = "local"  # local | cloud
    voice_reply_mode: str = "voice_if_started"  # always | voice_if_started | text
    wake_word_enabled: bool = False
    wake_word: str = "Hey Assistant"
    voice_style: str = "soft_friendly"
    voice_rate: int = 100
    voice_pitch: int = 100
    voice_volume: int = 90

    # Memory / logs / skills.
    audit_retention: str = "30d"  # 7d | 30d | 90d | forever | size
    learning_enabled: bool = True
    skills_enabled: bool = True
    allow_github_skills: bool = True
    allow_local_skills: bool = True

    @classmethod
    def load(cls) -> "Settings":
        path = config_dir() / "settings.json"
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            safe = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
            obj = cls(**safe)
        except Exception:
            return cls()

        # Safe migration/clamping from previous builds.
        obj.selected_agent = "hammer"
        obj.remember_agent = True
        obj.smart_agent_framework = "hammer2.1-primary-agent"
        if obj.interface_language not in {"ar", "en"}:
            # v1.7 had bilingual mode; migrate it to Arabic instead of mixed UI.
            obj.interface_language = "ar"
        obj.context_tokens = max(768, min(int(obj.context_tokens), 2048))
        obj.max_response_tokens = max(96, min(int(obj.max_response_tokens), 256))
        obj.threads = max(1, min(int(obj.threads), 2))
        obj.ai_timeout_seconds = max(30, min(int(obj.ai_timeout_seconds), 180))
        obj.hammer_retry_count = max(0, min(int(obj.hammer_retry_count), 2))
        obj.hammer_idle_minutes = max(0, min(int(obj.hammer_idle_minutes), 60))
        obj.approval_timeout_minutes = max(5, min(int(obj.approval_timeout_minutes), 1440))
        obj.drive_sync_interval_minutes = max(15, min(int(obj.drive_sync_interval_minutes), 1440))
        return obj

    def save(self) -> None:
        self.selected_agent = "hammer"
        self.remember_agent = True
        self.smart_agent_framework = "hammer2.1-primary-agent"
        if self.interface_language not in {"ar", "en"}:
            self.interface_language = "ar"
        path = config_dir() / "settings.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
