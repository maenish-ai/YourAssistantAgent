from __future__ import annotations

from tkinter import ttk

from ..agent.hammer_agent import HAMMER_MODEL_LABEL
from ..storage.db import ChatDB
from .i18n import ui_text


FRIENDLY = {
    "hammer_analyzing": ("🧠", "Hammer يحلل الطلب", "Hammer is analyzing"),
    "hammer_decision": ("🧭", "اختيار أداة", "Tool selected"),
    "hammer_tool_result": ("✅", "نتيجة الأداة", "Tool result"),
    "hammer_error": ("⚠", "Hammer استخدم المسار الاحتياطي", "Hammer fallback"),
    "agent_plan_preview": ("📋", "خطة تنتظر الموافقة", "Plan awaiting approval"),
    "agent_action_confirmed": ("✅", "تمت الموافقة", "Approved"),
    "agent_action_executed": ("✅", "تم تنفيذ الإجراء", "Action executed"),
    "agent_action_error": ("❌", "خطأ في الإجراء", "Action error"),
    "agent_action_cancelled": ("⛔", "تم الإلغاء", "Cancelled"),
    "facebook_connection": ("🟢", "Facebook متصل", "Facebook connected"),
    "facebook_connection_error": ("🔴", "مشكلة اتصال Facebook", "Facebook connection error"),
    "facebook_groups_discovered": ("🔎", "تم تحديث المجموعات", "Groups refreshed"),
    "facebook_rule_start": ("▶", "بدأت مهمة Facebook", "Facebook task started"),
    "facebook_opening": ("🌐", "فتح Facebook", "Opening Facebook"),
    "facebook_source_post_search": ("🔍", "البحث عن المنشور", "Finding source post"),
    "facebook_post_found": ("✅", "تم العثور على المنشور", "Source post found"),
    "facebook_group_share_start": ("📤", "جاري النشر إلى مجموعة", "Sharing to group"),
    "facebook_share": ("✅", "نتيجة مشاركة", "Share result"),
    "facebook_share_error": ("❌", "فشل مشاركة", "Share failed"),
    "facebook_rule_done": ("🏁", "انتهت المهمة", "Task completed"),
    "facebook_rule_error": ("❌", "خطأ في مهمة Facebook", "Facebook task error"),
    "chat_request": ("💬", "رسالة جديدة", "New message"),
    "chat_reply": ("🤖", "رد المساعد", "Assistant reply"),
    "ai_error": ("⚠", "خطأ AI", "AI error"),
    "settings_saved": ("⚙", "تم حفظ الإعدادات", "Settings saved"),
}


class ActivityView(ttk.Frame):
    """Live Status page: current state on top + auto-updating activity timeline."""

    def __init__(self, master, facebook=None, settings=None):
        super().__init__(master, padding=18)
        self.db = ChatDB()
        self.facebook = facebook
        self.settings = settings
        self.language = getattr(settings, "interface_language", "bilingual") if settings else "bilingual"
        self._last_id = None
        self._build()
        self.refresh()
        self.after(850, self._auto_refresh)

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        ttk.Label(self, text=ui_text("الحالة", "Status", self.language), style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            self,
            text=ui_text("تقرير حي يوضح أين وصل الوكيل لحظة بلحظة.", "Live report of what the agent is doing, step by step.", self.language),
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 12))

        cards = ttk.Frame(self)
        cards.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        for i in range(4):
            cards.columnconfigure(i, weight=1)
        self.agent_card = self._card(cards, 0, ui_text("الوكيل الذكي", "Smart Agent", self.language), HAMMER_MODEL_LABEL)
        self.fb_card = self._card(cards, 1, "Facebook", "—")
        self.groups_card = self._card(cards, 2, ui_text("المجموعات", "Groups", self.language), "0")
        self.tasks_card = self._card(cards, 3, ui_text("المهام", "Tasks", self.language), "0")

        wrap = ttk.Frame(self)
        wrap.grid(row=3, column=0, sticky="nsew")
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(1, weight=1)
        bar = ttk.Frame(wrap)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.now_label = ttk.Label(bar, text=ui_text("● جاهز", "● Ready", self.language), style="CardTitle.TLabel")
        self.now_label.pack(side="left")
        ttk.Button(bar, text=ui_text("تحديث", "Refresh", self.language), command=self.refresh).pack(side="right", padx=4)
        ttk.Button(bar, text=ui_text("مسح السجل", "Clear log", self.language), command=self.clear).pack(side="right", padx=4)

        self.tree = ttk.Treeview(wrap, columns=("time", "state", "detail"), show="headings")
        self.tree.heading("time", text=ui_text("الوقت", "Time", self.language))
        self.tree.heading("state", text=ui_text("الحالة", "State", self.language))
        self.tree.heading("detail", text=ui_text("التفاصيل", "Details", self.language))
        self.tree.column("time", width=145, stretch=False)
        self.tree.column("state", width=235, stretch=False)
        self.tree.column("detail", width=520, stretch=True)
        self.tree.grid(row=1, column=0, sticky="nsew")
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        sb.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=sb.set)

    def _card(self, parent, col, title, value):
        box = ttk.LabelFrame(parent, text=title, padding=10)
        box.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 5, 5 if col < 3 else 0))
        label = ttk.Label(box, text=value, style="CardTitle.TLabel", wraplength=190)
        label.pack(anchor="w")
        return label

    def _friendly(self, row: dict) -> tuple[str, str]:
        icon, ar, en = FRIENDLY.get(row["kind"], ("•", row["kind"], row["kind"]))
        return f"{icon} {ui_text(ar, en, self.language)}", str(row["detail"] or "")

    def refresh(self):
        rows = self.db.recent_activity(300)
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for row in rows:
            state, detail = self._friendly(row)
            self.tree.insert("", "end", values=(row["created_at"], state, detail))
        if rows:
            state, detail = self._friendly(rows[0])
            self.now_label.config(text=f"{state}: {detail[:120]}")
            self._last_id = rows[0]["id"]
        else:
            self.now_label.config(text=ui_text("● جاهز", "● Ready", self.language))
        if self.facebook:
            self.fb_card.config(text=self.facebook.status_text())
        self.groups_card.config(text=str(self.db.count_groups()))
        self.tasks_card.config(text=str(len(self.db.list_rules(500))))

    def clear(self):
        self.db.clear_activity()
        self.refresh()

    def _auto_refresh(self):
        if self.winfo_exists():
            self.refresh()
            self.after(850, self._auto_refresh)
