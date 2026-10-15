from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from ..agent.facebook_service import FacebookService
from ..storage.db import ChatDB
from .i18n import ui_text


class TasksView(ttk.Frame):
    def __init__(self, master, settings, facebook: FacebookService):
        super().__init__(master, padding=22)
        self.settings = settings
        self.language = settings.interface_language
        self.facebook = facebook
        self.db = ChatDB()
        self.view_mode = tk.StringVar(value="table")
        self.search_var = tk.StringVar()
        self.filter_var = tk.StringVar(value="all")
        self._build()
        self.refresh()

    def t(self, ar, en):
        return ui_text(ar, en, self.language)

    def _build(self):
        self.columnconfigure(0, weight=1); self.rowconfigure(3, weight=1)
        ttk.Label(self, text=self.t("المهام", "Tasks"), style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(self, text=self.t("جدولة، تشغيل، إيقاف مؤقت ومتابعة مهام الوكيل.", "Schedule, run, pause and review agent tasks."), style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(3, 14))

        bar = ttk.Frame(self); bar.grid(row=2, column=0, sticky="ew", pady=(0, 10)); bar.columnconfigure(0, weight=1)
        search = ttk.Entry(bar, textvariable=self.search_var); search.grid(row=0, column=0, sticky="ew"); search.bind("<KeyRelease>", lambda e: self.refresh())
        self.filter_combo = ttk.Combobox(bar, state="readonly", width=16, values=["all", "active", "paused"])
        self.filter_combo.set("all"); self.filter_combo.grid(row=0, column=1, padx=6); self.filter_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        ttk.Radiobutton(bar, text=self.t("جدول", "Table"), value="table", variable=self.view_mode, command=self.refresh).grid(row=0, column=2, padx=4)
        ttk.Radiobutton(bar, text=self.t("بطاقات", "Cards"), value="cards", variable=self.view_mode, command=self.refresh).grid(row=0, column=3, padx=4)
        ttk.Button(bar, text=self.t("تحديث", "Refresh"), command=self.refresh).grid(row=0, column=4, padx=(8, 0))

        self.content = ttk.Frame(self); self.content.grid(row=3, column=0, sticky="nsew"); self.content.columnconfigure(0, weight=1); self.content.rowconfigure(0, weight=1)

        actions = ttk.Frame(self); actions.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(actions, text=self.t("تشغيل الآن", "Run now"), style="Accent.TButton", command=self.run_selected).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text=self.t("تشغيل/إيقاف مؤقت", "Toggle pause"), command=self.toggle_selected).pack(side="left", padx=6)
        ttk.Button(actions, text=self.t("حذف", "Delete"), command=self.delete_selected).pack(side="left", padx=6)
        self.status = ttk.Label(actions, text="", style="Muted.TLabel"); self.status.pack(side="left", padx=12)

    def _rules(self):
        q = self.search_var.get().strip().casefold()
        f = self.filter_combo.get() if hasattr(self, "filter_combo") else "all"
        rules = self.db.list_rules(500)
        if q:
            rules = [r for r in rules if q in f"{r.get('name','')} {r.get('command_text','')} {r.get('group_keyword','')}".casefold()]
        if f == "active": rules = [r for r in rules if int(r.get("enabled", 1))]
        if f == "paused": rules = [r for r in rules if not int(r.get("enabled", 1))]
        return rules

    def _clear(self):
        for w in self.content.winfo_children(): w.destroy()
        self.tree = None

    def refresh(self):
        self._clear(); rules = self._rules()
        if self.view_mode.get() == "cards":
            canvas = tk.Canvas(self.content, highlightthickness=0); canvas.grid(row=0, column=0, sticky="nsew")
            sb = ttk.Scrollbar(self.content, orient="vertical", command=canvas.yview); sb.grid(row=0, column=1, sticky="ns"); canvas.configure(yscrollcommand=sb.set)
            wrap = ttk.Frame(canvas); win = canvas.create_window((0,0), window=wrap, anchor="nw")
            wrap.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
            for r in rules:
                box = ttk.LabelFrame(wrap, text=f"#{r['id']}  {r['name']}", padding=12); box.pack(fill="x", pady=5)
                state = self.t("نشطة", "Active") if int(r.get("enabled",1)) else self.t("متوقفة", "Paused")
                ttk.Label(box, text=f"{state} • {r.get('next_run_at') or '-'}\n{r.get('group_keyword') or self.t('كل الجروبات','All groups')}", wraplength=760).pack(anchor="w")
                ttk.Button(box, text=self.t("تشغيل", "Run"), command=lambda rid=int(r['id']): self._run_rule(rid)).pack(side="left", pady=(8,0))
                ttk.Button(box, text=self.t("إيقاف مؤقت/استئناف", "Pause/resume"), command=lambda rid=int(r['id']), en=bool(int(r.get('enabled',1))): self._toggle_rule(rid,en)).pack(side="left", padx=6, pady=(8,0))
        else:
            cols=("id","name","state","next","groups","interval")
            self.tree = ttk.Treeview(self.content, columns=cols, show="headings")
            headings={"id":"#","name":self.t("المهمة","Task"),"state":self.t("الحالة","State"),"next":self.t("التنفيذ القادم","Next run"),"groups":self.t("الاستهداف","Target"),"interval":self.t("الفاصل","Delay")}
            for c in cols: self.tree.heading(c,text=headings[c])
            self.tree.column("id",width=55,stretch=False); self.tree.column("name",width=230); self.tree.column("state",width=90); self.tree.column("next",width=170); self.tree.column("groups",width=160); self.tree.column("interval",width=90)
            self.tree.grid(row=0,column=0,sticky="nsew")
            sb=ttk.Scrollbar(self.content,orient="vertical",command=self.tree.yview); sb.grid(row=0,column=1,sticky="ns"); self.tree.configure(yscrollcommand=sb.set)
            for r in rules:
                state=self.t("نشطة","Active") if int(r.get("enabled",1)) else self.t("متوقفة","Paused")
                self.tree.insert("","end",iid=str(r['id']),values=(r['id'],r['name'],state,r.get('next_run_at') or '-',r.get('group_keyword') or self.t('الكل','All'),f"{r.get('interval_seconds',60)}s"))

    def _selected_id(self):
        if self.view_mode.get() != "table" or not self.tree:
            return None
        sel=self.tree.selection(); return int(sel[0]) if sel else None

    def run_selected(self):
        rid=self._selected_id()
        if rid is None:
            self.status.config(text=self.t("اختر مهمة من الجدول.","Select a task from the table.")); return
        self._run_rule(rid)

    def _run_rule(self, rid):
        if not messagebox.askyesno(self.t("تأكيد","Confirm"), self.t(f"تشغيل المهمة #{rid} الآن؟",f"Run task #{rid} now?"), parent=self): return
        result=self.facebook.run_rule_now(rid); self.status.config(text=result.message); self.refresh()

    def toggle_selected(self):
        rid=self._selected_id()
        if rid is None: return
        r=self.db.get_rule(rid); self._toggle_rule(rid,bool(int(r.get('enabled',1))) if r else False)

    def _toggle_rule(self,rid,enabled):
        self.db.set_rule_enabled(rid,not enabled); self.db.add_task_event(rid,"resumed" if not enabled else "paused"); self.refresh()

    def delete_selected(self):
        rid=self._selected_id()
        if rid is None:return
        if messagebox.askyesno(self.t("حذف المهمة","Delete task"), self.t("هل تريد حذف المهمة؟","Delete this task?"),parent=self):
            self.db.delete_rule(rid); self.refresh()
