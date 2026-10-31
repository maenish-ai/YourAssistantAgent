from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from ..storage.db import ChatDB
from .facebook_service import FacebookService
from .legacy_smart import SmartPlan
from .smol_contract import Tool as _SmolTool

if TYPE_CHECKING:
    from ..backup.service import BackupService

SMOLAGENTS_AVAILABLE = True


@dataclass
class ToolExecution:
    ok: bool
    text: str
    data: dict[str, Any] | None = None


class CountFacebookGroupsTool(_SmolTool):
    name = "count_facebook_groups"
    description = "Count saved Facebook groups whose name/tag contains a requested keyword. Empty keyword means all saved groups."
    inputs = {"keyword": {"type": "string", "description": "Group name/tag keyword, or empty string for all groups"}}
    output_type = "string"

    def __init__(self, db: ChatDB):
        self.db = db
        super().__init__()

    def forward(self, keyword: str = "") -> str:
        return str(self.db.count_groups(keyword or ""))


class DiscoverFacebookGroupsTool(_SmolTool):
    name = "discover_facebook_groups"
    description = "Discover groups joined by the connected Facebook account and save them locally."
    inputs = {}
    output_type = "string"

    def __init__(self, service: FacebookService):
        self.service = service
        super().__init__()

    def forward(self) -> str:
        return self.service.discover_groups().message


class FacebookStatusTool(_SmolTool):
    name = "facebook_status"
    description = "Return the current cached Facebook connection status without publishing anything."
    inputs = {}
    output_type = "string"

    def __init__(self, service: FacebookService):
        self.service = service
        super().__init__()

    def forward(self) -> str:
        return self.service.status_text()


class AppStatusTool(_SmolTool):
    name = "app_status"
    description = "Return a compact status summary for the assistant, Facebook, saved groups, tasks and backup."
    inputs = {}
    output_type = "string"

    def __init__(self, db: ChatDB, facebook: FacebookService, backup: BackupService | None):
        self.db = db
        self.facebook = facebook
        self.backup = backup
        super().__init__()

    def forward(self) -> str:
        backup_text = "unavailable"
        if self.backup is not None:
            try:
                st = self.backup.status()
                backup_text = f"{'connected' if st.connected else 'not_connected'}; last_backup={st.last_backup or 'none'}"
            except Exception as exc:
                backup_text = f"error:{type(exc).__name__}"
        return (
            f"Hammer=ready_or_lazy; Facebook={self.facebook.status_text()}; "
            f"groups={self.db.count_groups()}; tasks={len(self.db.list_rules(500))}; backup={backup_text}"
        )


class ListTasksTool(_SmolTool):
    name = "list_tasks"
    description = "List saved scheduled tasks."
    inputs = {}
    output_type = "string"

    def __init__(self, db: ChatDB):
        self.db = db
        super().__init__()

    def forward(self) -> str:
        rules = self.db.list_rules(30)
        if not rules:
            return "No saved tasks"
        return "\n".join(
            f"#{r['id']} {r['name']} | {'active' if int(r.get('enabled', 1)) else 'paused'} | next={r.get('next_run_at') or '-'}"
            for r in rules
        )


class BackupStatusTool(_SmolTool):
    name = "backup_status"
    description = "Return encrypted local backup and Google Drive sync status."
    inputs = {}
    output_type = "string"

    def __init__(self, backup: BackupService | None):
        self.backup = backup
        super().__init__()

    def forward(self) -> str:
        if self.backup is None:
            return "Backup service unavailable"
        st = self.backup.status()
        return (
            f"drive={'connected' if st.connected else 'not_connected'}; account={st.account or '-'}; "
            f"last_backup={st.last_backup or '-'}; last_sync={st.last_sync or '-'}"
        )


class SaveFacebookRuleTool(_SmolTool):
    name = "save_facebook_share_rule"
    description = "Save an approved Facebook group-sharing schedule. This tool is called only after user confirmation."
    inputs = {
        "name": {"type": "string", "description": "Short rule name"},
        "command_text": {"type": "string", "description": "Original user instruction"},
        "source_page_url": {"type": "string", "description": "Facebook source page URL"},
        "weekdays": {"type": "array", "description": "Weekday numbers Monday=0..Sunday=6; use [] for daily"},
        "run_time": {"type": "string", "description": "24-hour HH:MM"},
        "run_once_at": {"type": "string", "description": "ISO local datetime for one-time run or empty string"},
        "post_mode": {"type": "string", "description": "fixed or rotation"},
        "post_offset": {"type": "integer", "description": "0=latest, 1=previous"},
        "group_keyword": {"type": "string", "description": "Saved-group filter keyword or empty for all"},
        "max_groups": {"type": "integer", "description": "Maximum groups"},
        "interval_seconds": {"type": "integer", "description": "Delay between groups, minimum 30"},
        "no_repeat_days": {"type": "integer", "description": "Do not repeat same post/group within this many days"},
        "share_mode": {"type": "string", "description": "native_share"},
    }
    output_type = "string"

    def __init__(self, service: FacebookService):
        self.service = service
        super().__init__()

    def forward(
        self,
        name: str,
        command_text: str,
        source_page_url: str,
        weekdays: list,
        run_time: str,
        run_once_at: str,
        post_mode: str,
        post_offset: int,
        group_keyword: str,
        max_groups: int,
        interval_seconds: int,
        no_repeat_days: int,
        share_mode: str,
    ) -> str:
        plan = SmartPlan(
            name=str(name or "Smart Facebook rule"),
            command_text=str(command_text or ""),
            source_page_url=str(source_page_url or ""),
            weekdays=[int(x) for x in (weekdays or [])],
            run_time=str(run_time or "20:00"),
            run_once_at=str(run_once_at or ""),
            post_mode=str(post_mode or "fixed"),
            post_offset=max(0, int(post_offset or 0)),
            group_keyword=str(group_keyword or ""),
            max_groups=max(1, min(int(max_groups or 100), 500)),
            interval_seconds=max(30, int(interval_seconds or 60)),
            no_repeat_days=max(0, int(no_repeat_days or 14)),
            share_mode="native_share",
        )
        return self.service.save_rule(plan).message


class RunFacebookRuleNowTool(_SmolTool):
    name = "run_facebook_rule_now"
    description = "Run a saved Facebook Smart Agent rule immediately in the background."
    inputs = {"rule_id": {"type": "integer", "description": "Saved rule ID"}}
    output_type = "string"

    def __init__(self, service: FacebookService):
        self.service = service
        super().__init__()

    def forward(self, rule_id: int) -> str:
        return self.service.run_rule_now(int(rule_id)).message


class ToolRegistry:
    """Allow-listed application tools. No arbitrary code execution is exposed."""

    def __init__(self, db: ChatDB, facebook: FacebookService, backup: BackupService | None = None):
        tools = [
            CountFacebookGroupsTool(db),
            DiscoverFacebookGroupsTool(facebook),
            FacebookStatusTool(facebook),
            AppStatusTool(db, facebook, backup),
            ListTasksTool(db),
            BackupStatusTool(backup),
            SaveFacebookRuleTool(facebook),
            RunFacebookRuleNowTool(facebook),
        ]
        self.tools = {t.name: t for t in tools}

    def schema_text(self) -> str:
        rows = []
        for t in self.tools.values():
            args = ", ".join(t.inputs.keys()) if getattr(t, "inputs", None) else "none"
            rows.append(f"- {t.name}({args}): {t.description}")
        return "\n".join(rows)

    def execute(self, name: str, arguments: dict[str, Any] | None = None) -> ToolExecution:
        tool = self.tools.get(name)
        if not tool:
            return ToolExecution(False, f"Unknown tool: {name}")
        try:
            result = tool.forward(**(arguments or {}))
            return ToolExecution(True, str(result))
        except Exception as exc:
            return ToolExecution(False, f"{type(exc).__name__}: {exc}")
