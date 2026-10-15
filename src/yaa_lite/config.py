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
    # Kept for database/backward compatibility. v1.7 exposes one assistant only.
    selected_agent: str = "hammer"
    remember_agent: bool = True

    # Interface can be Arabic, English, or bilingual. Bilingual is the default
    # because the user explicitly asked to see both labels.
    interface_language: str = "bilingual"

    ai_timeout_seconds: int = 75
    context_tokens: int = 768
    max_response_tokens: int = 160
    threads: int = 2
    drive_backup_folder: str = ""
    auto_backup: bool = True
    retry_ai_once: bool = True

    smart_agent_enabled: bool = True
    confirm_external_actions: bool = True
    default_source_page: str = ""
    facebook_browser_choice: str = "auto"
    smart_agent_framework: str = "hammer2.1-tool-router"

    @classmethod
    def load(cls) -> "Settings":
        path = config_dir() / "settings.json"
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            safe = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
            obj = cls(**safe)
            obj.context_tokens = max(512, min(int(obj.context_tokens), 1024))
            obj.max_response_tokens = max(96, min(int(obj.max_response_tokens), 256))
            obj.threads = max(1, min(int(obj.threads), 2))
            obj.ai_timeout_seconds = max(30, min(int(obj.ai_timeout_seconds), 150))
            if obj.interface_language not in {"bilingual", "ar", "en"}:
                obj.interface_language = "bilingual"
            # Migrate all previous visible agent choices to the single Hammer assistant.
            obj.selected_agent = "hammer"
            obj.remember_agent = True
            obj.smart_agent_framework = "hammer2.1-tool-router"
            return obj
        except Exception:
            return cls()

    def save(self) -> None:
        self.selected_agent = "hammer"
        self.remember_agent = True
        self.smart_agent_framework = "hammer2.1-tool-router"
        path = config_dir() / "settings.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
