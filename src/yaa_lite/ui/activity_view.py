from __future__ import annotations

import time
from tkinter import ttk

from ..agent.hammer_agent import HAMMER_MODEL_LABEL
from ..storage.db import ChatDB
from .i18n import ui_text

FRIENDLY = {
    "hammer_analyzing": ("🧠", "Hammer يحلل الطلب", "Hammer is analyzing"),
    "hammer_decision": ("🧭", "اختيار أداة", "Tool selected"),
    "hammer_tool_result": ("✅", "نتيجة الأداة", "Tool result"),
    "hammer_unknown_tool": ("⚠", "أداة غير معروفة", "Unknown tool"),
    "agent_plan_preview": ("📋", "خطة تنتظر الموافقة", "Plan awaiting approval"),
    "agent_action_confirmed": ("✅", "تمت الموافقة", "Approved"),
    "agent_action_executed": ("✅", "تم التنفيذ", "Action executed"),
    "agent_action_error": ("❌", "خطأ في الإجراء", "Action error"),
    "agent_action_cancelled": ("⛔", "تم الإلغاء", "Cancelled"),
    "facebook_connection": ("🟢", "Facebook متصل", "Facebook connected"),
    "facebook_connection_error": ("🔴", "مشكلة اتصال Facebook", "Facebook connection error"),
    "facebook_groups_discovered": ("🔎", "تم تحديث الجروبات", "Groups refreshed"),
    "facebook_rule_start": ("▶", "بدأت مهمة Facebook", "Facebook task started"),
    "facebook_rule_paused": ("⏸", "تم إيقاف المهمة مؤقتًا", "Task paused"),
    "facebook_rule_resumed": ("▶", "تم استئناف المهمة", "Task resumed"),
    "facebook_rule_stop_requested": ("⏹", "طلب إيقاف المهمة", "Stop requested"),
    "facebook_rule_cancelled": ("⏹", "توقفت المهمة", "Task stopped"),
    "facebook_opening": ("🌐", "فتح Facebook", "Opening Facebook"),
    "facebook_source_post_search": ("🔍", "البحث عن المنشور", "Finding source post"),
    "facebook_post_found": ("✅", "تم العثور على المنشور", "Source post found"),
    "facebook_group_share_start": ("📤", "جاري النشر إلى جروب", "Sharing to group"),
    "facebook_share": ("✅", "نتيجة المشاركة", "Share result"),
    "facebook_share_error": ("❌", "فشل المشاركة", "Share failed"),
    "facebook_rule_done": ("🏁", "انتهت المهمة", "Task completed"),
    "facebook_rule_error": ("❌", "خطأ في مهمة Facebook", "Facebook task error"),
    "browser_extension_connected": ("🌐", "المتصفح العادي متصل", "Open browser connected"),
    "backup_created": ("💾", "تم إنشاء نسخة احتياطية", "Backup created"),
    "backup_restored": ("↩", "تمت الاستعادة", "Backup restored"),
    "drive_connected": ("☁", "Google Drive متصل", "Google Drive connected"),
    "drive_sync": ("☁", "تمت مزامنة Drive", "Drive synced"),
    "chat_request": ("💬", "رسالة جديدة", "New message"),
    "chat_reply": ("🤖", "رد Hammer", "Hammer reply"),
    "ai_error": ("⚠", "خطأ Hammer", "Hammer error"),
    "hammer_idle_unload": ("💤", "تم إخراج Hammer من الذاكرة", "Hammer unloaded from memory"),
    "settings_saved": ("⚙", "تم حفظ الإعدادات", "Settings saved"),
}


class ActivityView(ttk.Frame):
    """Live Status page: current step + progress + timeline + task controls."""

    def __init__(self, master, facebook=None, settings=None, runtime=None, backup=None, browser_bridge=None):
        super().__init__(master, padding=20)
        self.db = ChatDB()
        self.facebook = facebook
        self.settings = settings
        self.runtime = runtime
        self.backup = backup
        self.browser_bridge = browser_bridge
        self.language = getattr(settings, "interface_language", "ar") if settings else "ar"
        self._build(); self.refresh(); self.after(850, self._auto_refresh)

    def t(self, ar, en): return ui_text(ar, en, self.language)

    def _build(self):
        self.columnconfigure(0, weight=1); self.rowconfigure(5, weight=1)
        ttk.Label(self, text=self.t("الحالة", "Status"), style="Title.TLabel").grid(row=0,column=0,sticky="w")
        ttk.Label(self,text=self.t("متابعة مباشرة لكل خطوة ينفذها الوكيل.","Live view of every step the agent is executing."),style="Muted.TLabel").grid(row=1,column=0,sticky="w",pady=(3,12))

        cards=ttk.Frame(self); cards.grid(row=2,column=0,sticky="ew",pady=(0,10))
        for i in range(4):cards.columnconfigure(i,weight=1)
        self.agent_card=self._card(cards,0,"Hammer",HAMMER_MODEL_LABEL)
        self.fb_card=self._card(cards,1,"Facebook","—")
        self.groups_card=self._card(cards,2,self.t("الجروبات","Groups"),"0")
        self.backup_card=self._card(cards,3,self.t("النسخ الاحتياطي","Backup"),"—")

        current=ttk.LabelFrame(self,text=self.t("المهمة الحالية","Current task"),padding=12); current.grid(row=3,column=0,sticky="ew",pady=(0,10)); current.columnconfigure(0,weight=1)
        self.now_label=ttk.Label(current,text=self.t("لا توجد مهمة شغالة","No active task"),style="CardTitle.TLabel"); self.now_label.grid(row=0,column=0,sticky="w")
        self.progress=ttk.Progressbar(current,maximum=100); self.progress.grid(row=1,column=0,sticky="ew",pady=(8,5))
        self.progress_text=ttk.Label(current,text="",style="Muted.TLabel"); self.progress_text.grid(row=2,column=0,sticky="w")
        controls=ttk.Frame(current); controls.grid(row=0,column=1,rowspan=3,sticky="e",padx=(12,0))
        ttk.Button(controls,text=self.t("إيقاف مؤقت","Pause"),command=self.pause).pack(side="left",padx=3)
        ttk.Button(controls,text=self.t("استئناف","Resume"),command=self.resume).pack(side="left",padx=3)
        ttk.Button(controls,text=self.t("إيقاف","Stop"),command=self.stop).pack(side="left",padx=3)

        bar=ttk.Frame(self); bar.grid(row=4,column=0,sticky="ew",pady=(0,6))
        ttk.Label(bar,text=self.t("سجل مباشر","Live timeline"),style="CardTitle.TLabel").pack(side="left")
        ttk.Button(bar,text=self.t("تحديث","Refresh"),command=self.refresh).pack(side="right",padx=4)
        ttk.Button(bar,text=self.t("مسح السجل","Clear log"),command=self.clear).pack(side="right",padx=4)

        self.tree=ttk.Treeview(self,columns=("time","state","detail"),show="headings")
        self.tree.heading("time",text=self.t("الوقت","Time"));self.tree.heading("state",text=self.t("الحالة","State"));self.tree.heading("detail",text=self.t("التفاصيل","Details"))
        self.tree.column("time",width=145,stretch=False);self.tree.column("state",width=220,stretch=False);self.tree.column("detail",width=560,stretch=True)
        self.tree.grid(row=5,column=0,sticky="nsew")
        sb=ttk.Scrollbar(self,orient="vertical",command=self.tree.yview);sb.grid(row=5,column=1,sticky="ns");self.tree.config(yscrollcommand=sb.set)

    def _card(self,parent,col,title,value):
        box=ttk.LabelFrame(parent,text=title,padding=10);box.grid(row=0,column=col,sticky="nsew",padx=(0 if col==0 else 5,5 if col<3 else 0));lbl=ttk.Label(box,text=value,style="CardTitle.TLabel",wraplength=180);lbl.pack(anchor="w");return lbl

    def _friendly(self,row):
        icon,ar,en=FRIENDLY.get(row["kind"],("•",row["kind"],row["kind"]));return f"{icon} {self.t(ar,en)}",str(row["detail"] or "")

    def pause(self):
        if self.facebook:self.facebook.pause_current()
    def resume(self):
        if self.facebook:self.facebook.resume_current()
    def stop(self):
        if self.facebook:self.facebook.stop_current()

    def refresh(self):
        rows=self.db.recent_activity(350)
        for iid in self.tree.get_children():self.tree.delete(iid)
        for row in rows:
            state,detail=self._friendly(row);self.tree.insert("","end",values=(row["created_at"],state,detail))
        self.agent_card.config(text=self.t("جاهز" if self.runtime and self.runtime.loaded_profile else "جاهز عند الطلب","Ready" if self.runtime and self.runtime.loaded_profile else "Ready on demand"))
        if self.facebook:
            self.fb_card.config(text=self.facebook.status_text());st=self.facebook.current_status()
            if st["running"]:
                self.now_label.config(text=f"#{st['active_rule_id']} • {st['step']}")
                total=max(1,int(st["total"] or 0));done=int(st["done"] or 0);pct=min(100,done*100/total);self.progress["value"]=pct
                elapsed=int(time.time()-st["started_at"]) if st.get("started_at") else 0
                self.progress_text.config(text=self.t(f"{done}/{st['total']} • {pct:.0f}% • مضى {elapsed} ثانية",f"{done}/{st['total']} • {pct:.0f}% • {elapsed}s elapsed"))
            else:
                self.now_label.config(text=self.t("لا توجد مهمة شغالة","No active task"));self.progress["value"]=0;self.progress_text.config(text="")
        self.groups_card.config(text=str(self.db.count_groups()))
        if self.backup:
            bst=self.backup.status();self.backup_card.config(text=self.t("متصل" if bst.connected else "محلي فقط","Connected" if bst.connected else "Local only"))

    def clear(self):self.db.clear_activity();self.refresh()
    def _auto_refresh(self):
        if self.winfo_exists():self.refresh();self.after(850,self._auto_refresh)
