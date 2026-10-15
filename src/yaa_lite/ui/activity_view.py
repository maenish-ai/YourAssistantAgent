from __future__ import annotations

from tkinter import ttk

from ..storage.db import ChatDB


class ActivityView(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=16)
        self.db = ChatDB()
        self._build()
        self.refresh()
        self.after(2500, self._auto_refresh)

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(bar, text="Activity / النشاط", style="CardTitle.TLabel").pack(side="left")
        ttk.Button(bar, text="Refresh", command=self.refresh).pack(side="right", padx=4)
        ttk.Button(bar, text="Clear", command=self.clear).pack(side="right", padx=4)

        self.tree = ttk.Treeview(self, columns=("time", "kind", "detail"), show="headings")
        self.tree.heading("time", text="Time")
        self.tree.heading("kind", text="Type")
        self.tree.heading("detail", text="Details")
        self.tree.column("time", width=145, stretch=False)
        self.tree.column("kind", width=130, stretch=False)
        self.tree.column("detail", width=560, stretch=True)
        self.tree.grid(row=1, column=0, sticky="nsew")
        sb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        sb.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=sb.set)

    def refresh(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for row in self.db.recent_activity(250):
            self.tree.insert("", "end", values=(row["created_at"], row["kind"], row["detail"]))

    def clear(self):
        self.db.clear_activity()
        self.refresh()

    def _auto_refresh(self):
        if self.winfo_exists():
            self.refresh()
            self.after(2500, self._auto_refresh)
