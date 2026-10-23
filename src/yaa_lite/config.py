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
    # Legacy profile labels remain for database/backward compatibility.
    # Actual reasoning is performed by GroqCloud; no local model is loaded.
    selected_agent: str = "qwen"
    remember_agent: bool = True
    smart_agent_framework: str = "qwen3-1.7b-primary-agent"

    # First run / UI.
    first_run_complete: bool = False
    interface_language: str = "ar"
    appearance: str = "system"
    startup_page: str = "home"
    last_page: str = "home"
    close_behavior: str = "exit"
    start_with_windows: str = "off"

    # Cloud-model request settings; these fields keep legacy names for migration.
    smart_agent_enabled: bool = True
    ai_timeout_seconds: int = 120
    context_tokens: int = 3072
    max_response_tokens: int = 240
    threads: int = 2
    hammer_retry_count: int = 2  # legacy field name; applies to Qwen retries
    hammer_idle_minutes: int = 0  # cloud mode; no local AI process to keep warm
    performance_mode: str = "balanced"
    reply_language: str = "message"
    arabic_dialect: str = "jordanian"
    assistant_name: str = "Assistant"
    personality_style: str = "friendly"
    personality_prompt: str = ""
    suggestion_level: str = "medium"

    # Security / approvals.
    password_mode: str = "every_launch"
    approval_timeout_minutes: int = 30
    confirmation_policy: str = "always"
    confirmation_group_threshold: int = 10
    confirm_external_actions: bool = True

    # Facebook / browser.
    default_source_page: str = ""
    facebook_auto_check: bool = False
    facebook_browser_choice: str = "auto"
    facebook_browser_custom_path: str = ""
    facebook_browser_mode: str = "extension_first"
    facebook_interval_min_seconds: int = 50
    facebook_interval_max_seconds: int = 90
    facebook_hourly_limit: int = 30
    facebook_daily_limit: int = 120
    facebook_no_repeat_days: int = 14
    facebook_pending_check_minutes: int = 60

    # Backup / Google Drive.
    background_tasks_enabled: bool = False  # v2.9: explicit opt-in for unattended tasks
    lightweight_defaults_v290: bool = True
    auto_backup: bool = False
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

    # Cloud STT/TTS are provided by v2.8 voice service; legacy options preserved.
    voice_enabled: bool = True
    voice_input_device: str = "auto"  # exact device label; auto means Windows default input
    voice_backend: str = "local"
    voice_reply_mode: str = "text"
    wake_word_enabled: bool = False
    wake_word: str = "Hey Assistant"
    voice_style: str = "soft_friendly"
    voice_rate: int = 100
    voice_pitch: int = 100
    voice_volume: int = 90

    # Memory / logs / skills.
    audit_retention: str = "30d"
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
            legacy_framework = str(raw.get("smart_agent_framework") or "")
            safe = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
            obj = cls(**safe)
            # v2.9 one-time SAFE migration: persistent tasks and backups are
            # preserved, but unattended work stays off until explicitly enabled.
            # This is intentional after reports of Windows freezing during idle.
            if not raw.get("lightweight_defaults_v290", False):
                obj.close_behavior = "exit"
                obj.start_with_windows = "off"
                obj.facebook_auto_check = False
                obj.auto_backup = False
                obj.background_tasks_enabled = False
                obj.lightweight_defaults_v290 = True
        except Exception:
            return cls()

        # Migration from Hammer builds: switch the brain, keep it warm, and make
        # push-to-talk available without forcing the user through Settings first.
        migrating_from_hammer = not legacy_framework.startswith("qwen3-")
        obj.selected_agent = "qwen"
        obj.remember_agent = True
        obj.smart_agent_framework = "qwen3-1.7b-primary-agent"
        if migrating_from_hammer:
            obj.hammer_idle_minutes = 0
            obj.voice_enabled = True
            # Text replies are mandatory in v3.0. Mic is dictation-only.

        if obj.interface_language not in {"ar", "en"}:
            obj.interface_language = "ar"
        obj.context_tokens = max(1536, min(int(obj.context_tokens), 4096))
        if migrating_from_hammer and obj.context_tokens <= 2048:
            obj.context_tokens = 3072
        obj.max_response_tokens = max(96, min(int(obj.max_response_tokens), 384))
        obj.threads = max(1, min(int(obj.threads), 4))
        obj.ai_timeout_seconds = max(45, min(int(obj.ai_timeout_seconds), 240))
        obj.hammer_retry_count = max(0, min(int(obj.hammer_retry_count), 2))
        obj.hammer_idle_minutes = max(0, min(int(obj.hammer_idle_minutes), 60))
        # This release intentionally never reads responses aloud.
        obj.voice_reply_mode = "text"
        obj.approval_timeout_minutes = max(5, min(int(obj.approval_timeout_minutes), 1440))
        obj.drive_sync_interval_minutes = max(15, min(int(obj.drive_sync_interval_minutes), 1440))
        return obj

    def save(self) -> None:
        self.selected_agent = "qwen"
        self.remember_agent = True
        self.smart_agent_framework = "qwen3-1.7b-primary-agent"
        if self.interface_language not in {"ar", "en"}:
            self.interface_language = "ar"
        path = config_dir() / "settings.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
