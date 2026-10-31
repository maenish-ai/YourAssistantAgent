from __future__ import annotations

import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

from ..backup.service import BackupService
from .i18n import ui_text


class BackupView(ttk.Frame):
    def __init__(self, master, settings, backup: BackupService):
        super().__init__(master, padding=22)
        self.settings = settings
        self.language = settings.interface_language
        self.backup = backup
        self._busy = False
        self._remote_rows: dict[str, dict] = {}
        self._build(); self.refresh()

    def t(self, ar, en): return ui_text(ar, en, self.language)

    def _build(self):
        self.columnconfigure(0, weight=1); self.rowconfigure(4, weight=1)
        ttk.Label(self, text=self.t("النسخ الاحتياطي", "Backup"), style="Title.TLabel").grid(row=0,column=0,sticky="w")
        ttk.Label(self, text=self.t("نسخ مشفرة محليًا مع مزامنة Google Drive اختيارية وسجل إصدارات.", "Encrypted local backup with optional Google Drive sync and version history."), style="Muted.TLabel").grid(row=1,column=0,sticky="w",pady=(3,14))

        cards=ttk.Frame(self); cards.grid(row=2,column=0,sticky="ew")
        for i in range(3): cards.columnconfigure(i,weight=1)
        self.drive_card=self._card(cards,0,"Google Drive","—")
        self.last_card=self._card(cards,1,self.t("آخر نسخة","Last backup"),"—")
        self.sync_card=self._card(cards,2,self.t("آخر مزامنة","Last sync"),"—")

        controls=ttk.LabelFrame(self,text=self.t("الإدارة","Management"),padding=12); controls.grid(row=3,column=0,sticky="ew",pady=(14,10))
        ttk.Button(controls,text=self.t("نسخ الآن","Backup now"),style="Accent.TButton",command=lambda:self._run("backup")).pack(side="left",padx=4)
        ttk.Button(controls,text=self.t("ربط Google Drive","Connect Google Drive"),command=lambda:self._run("connect")).pack(side="left",padx=4)
        ttk.Button(controls,text=self.t("مزامنة الآن","Sync now"),command=lambda:self._run("sync")).pack(side="left",padx=4)
        ttk.Button(controls,text=self.t("تحديث نسخ Drive","Refresh Drive backups"),command=lambda:self._run("remote")).pack(side="left",padx=4)
        ttk.Button(controls,text=self.t("استعادة ملف محلي","Restore local file"),command=self.restore_local).pack(side="left",padx=4)
        ttk.Button(controls,text=self.t("استعادة من Drive","Restore from Drive"),command=self.restore_remote).pack(side="left",padx=4)
        ttk.Button(controls,text=self.t("فصل Drive","Disconnect Drive"),command=self.disconnect).pack(side="left",padx=4)
        self.status=ttk.Label(controls,text="",style="Muted.TLabel"); self.status.pack(side="left",padx=10)

        body=ttk.Frame(self); body.grid(row=4,column=0,sticky="nsew"); body.columnconfigure(0,weight=1); body.columnconfigure(1,weight=1); body.rowconfigure(0,weight=1)
        local=ttk.LabelFrame(body,text=self.t("النسخ المحلية","Local backups"),padding=10); local.grid(row=0,column=0,sticky="nsew",padx=(0,6)); local.rowconfigure(0,weight=1); local.columnconfigure(0,weight=1)
        self.local_tree=ttk.Treeview(local,columns=("name","size"),show="headings",selectmode="browse"); self.local_tree.heading("name",text=self.t("الملف","File")); self.local_tree.heading("size",text=self.t("الحجم","Size")); self.local_tree.column("name",width=320); self.local_tree.column("size",width=100,stretch=False); self.local_tree.grid(row=0,column=0,sticky="nsew")
        sb=ttk.Scrollbar(local,orient="vertical",command=self.local_tree.yview); sb.grid(row=0,column=1,sticky="ns"); self.local_tree.config(yscrollcommand=sb.set)

        right=ttk.Frame(body); right.grid(row=0,column=1,sticky="nsew",padx=(6,0)); right.columnconfigure(0,weight=1); right.rowconfigure(0,weight=1)
        remote=ttk.LabelFrame(right,text=self.t("إصدارات Google Drive","Google Drive versions"),padding=10); remote.grid(row=0,column=0,sticky="nsew"); remote.rowconfigure(0,weight=1); remote.columnconfigure(0,weight=1)
        self.remote_tree=ttk.Treeview(remote,columns=("name","created"),show="headings",selectmode="browse"); self.remote_tree.heading("name",text=self.t("النسخة","Backup")); self.remote_tree.heading("created",text=self.t("التاريخ","Date")); self.remote_tree.column("name",width=290); self.remote_tree.column("created",width=145,stretch=False); self.remote_tree.grid(row=0,column=0,sticky="nsew")
        sb2=ttk.Scrollbar(remote,orient="vertical",command=self.remote_tree.yview); sb2.grid(row=0,column=1,sticky="ns"); self.remote_tree.config(yscrollcommand=sb2.set)

        info=ttk.LabelFrame(right,text=self.t("التشفير والاسترداد","Encryption & recovery"),padding=12); info.grid(row=1,column=0,sticky="ew",pady=(10,0))
        ttk.Label(info,text=self.t("كل نسخة تُشفّر قبل رفعها. كلمة المرور أو Recovery Key الأصليان يمكنهما فتح نسخة على جهاز جديد.", "Every backup is encrypted before upload. The original password or Recovery Key can open it on a new device."),style="Muted.TLabel",wraplength=420).pack(anchor="w")
        ttk.Label(info,text=self.t("بيانات جلسة Facebook لا تدخل النسخة إلا إذا فعّلت مزامنة بيانات الدخول صراحةً.", "Facebook session data is excluded unless credential sync is explicitly enabled."),style="Muted.TLabel",wraplength=420).pack(anchor="w",pady=(6,0))

    def _card(self,parent,col,title,value):
        box=ttk.LabelFrame(parent,text=title,padding=10); box.grid(row=0,column=col,sticky="nsew",padx=(0 if col==0 else 5,5 if col<2 else 0)); lbl=ttk.Label(box,text=value,style="CardTitle.TLabel",wraplength=220); lbl.pack(anchor="w"); return lbl

    def _run(self,action):
        if self._busy:return
        self._busy=True; self.status.config(text=self.t("جاري التنفيذ…","Working…"))
        def work():
            try:
                if action=="backup": msg=str(self.backup.create_local_backup())
                elif action=="connect": msg=self.backup.connect_drive() or self.t("تم الربط","Connected")
                elif action=="remote":
                    rows=self.backup.list_drive_backups(); self.after(0,lambda r=rows:self._set_remote(r)); msg=self.t(f"تم العثور على {len(rows)} نسخة",f"Found {len(rows)} backup(s)")
                else: msg=f"Drive file: {self.backup.sync_now()}"
                self.after(0,lambda m=msg:self._done(m,False))
            except Exception as exc:
                self.after(0,lambda e=exc:self._done(f"{type(e).__name__}: {e}",True))
        threading.Thread(target=work,daemon=True,name=f"yaa-backup-{action}").start()

    def _set_remote(self, rows):
        self._remote_rows={str(r.get("id")):r for r in rows if r.get("id")}
        for iid in self.remote_tree.get_children(): self.remote_tree.delete(iid)
        for rid,r in self._remote_rows.items():
            self.remote_tree.insert("","end",iid=rid,values=(r.get("name") or rid,r.get("createdTime") or r.get("modifiedTime") or "—"))

    def _done(self,msg,error):
        self._busy=False; self.status.config(text=msg); self.refresh(local_only=True)
        if error: messagebox.showerror(self.t("خطأ","Error"),msg,parent=self)

    def restore_local(self):
        path=filedialog.askopenfilename(title=self.t("اختر نسخة احتياطية","Choose backup"),filetypes=[("YAA Backup","*.yaa-backup"),("All files","*.*")])
        if not path:return
        if not messagebox.askyesno(self.t("تأكيد الاستعادة","Confirm restore"),self.t("الاستعادة ستكتب فوق بيانات البرنامج الحالية. هل تكمل؟","Restore will replace current app data. Continue?"),parent=self):return
        try:
            self.backup.restore_local_backup(Path(path)); self.status.config(text=self.t("تمت الاستعادة. أعد تشغيل البرنامج.","Restored. Restart the app."))
        except Exception as exc: messagebox.showerror(self.t("خطأ","Error"),str(exc),parent=self)

    def restore_remote(self):
        sel=self.remote_tree.selection()
        if not sel:
            messagebox.showinfo(self.t("استعادة","Restore"),self.t("اختر نسخة من قائمة Drive أولًا.","Select a Drive backup first."),parent=self);return
        rid=sel[0]
        if not messagebox.askyesno(self.t("تأكيد الاستعادة","Confirm restore"),self.t("سيتم تنزيل النسخة واستعادة بياناتها. هل تكمل؟","Download and restore this version?"),parent=self):return
        def work():
            try:
                try:
                    self.backup.restore_drive_backup(rid)
                except Exception:
                    # This is the common cross-device case: current device has a
                    # different master key. Ask on the UI thread for original secret.
                    holder={}; ev=threading.Event()
                    def ask():
                        use_rec=messagebox.askyesno(self.t("طريقة الاسترداد","Recovery method"),self.t("هل ستستخدم Recovery Key؟\nاختر لا لاستخدام كلمة المرور الأصلية.","Use the Recovery Key?\nChoose No to use the original app password."),parent=self)
                        secret=simpledialog.askstring(self.t("بيانات الاسترداد","Recovery credential"),self.t("أدخل Recovery Key","Enter Recovery Key") if use_rec else self.t("أدخل كلمة المرور الأصلية","Enter original password"),show="" if use_rec else "•",parent=self)
                        holder.update(secret=secret,use_rec=use_rec);ev.set()
                    self.after(0,ask);ev.wait()
                    if not holder.get("secret"): raise RuntimeError(self.t("تم إلغاء الاستعادة","Restore cancelled"))
                    self.backup.restore_drive_backup(rid,secret=holder["secret"],use_recovery=holder["use_rec"])
                self.after(0,lambda:self._done(self.t("تمت الاستعادة. أعد تشغيل البرنامج.","Restored. Restart the app."),False))
            except Exception as exc:
                self.after(0,lambda e=exc:self._done(f"{type(e).__name__}: {e}",True))
        threading.Thread(target=work,daemon=True,name="yaa-drive-restore").start()

    def disconnect(self):
        if messagebox.askyesno(self.t("فصل Google Drive","Disconnect Google Drive"),self.t("هل تريد حذف رمز الاتصال المحلي؟","Remove the local Drive connection token?"),parent=self):
            self.backup.disconnect_drive(); self._set_remote([]); self.refresh()

    def refresh(self, local_only=False):
        st=self.backup.status(); self.drive_card.config(text=(st.account or self.t("متصل","Connected")) if st.connected else self.t("غير متصل","Not connected")); self.last_card.config(text=st.last_backup or "—"); self.sync_card.config(text=st.last_sync or "—")
        for iid in self.local_tree.get_children(): self.local_tree.delete(iid)
        for p in self.backup.list_local_backups():
            try:size=f"{p.stat().st_size/1024/1024:.1f} MB"
            except Exception:size="—"
            self.local_tree.insert("","end",values=(p.name,size))
        if st.connected and not local_only and not self._remote_rows:
            self._run("remote")
