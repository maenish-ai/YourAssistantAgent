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
    selected_agent: str = ""
    remember_agent: bool = False
    ai_timeout_seconds: int = 75
    context_tokens: int = 1024
    max_response_tokens: int = 220
    threads: int = 2
    drive_backup_folder: str = ""
    auto_backup: bool = True

    @classmethod
    def load(cls) -> "Settings":
        path = config_dir() / "settings.json"
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            safe = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
            return cls(**safe)
        except Exception:
            return cls()

    def save(self) -> None:
        path = config_dir() / "settings.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
