from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from dataclasses import replace
from pathlib import Path

from ..agent.hammer_agent import HAMMER_LICENSE, HAMMER_MODEL_LABEL
from ..config import Settings
from ..security.manager import SecurityManager, SecurityError
from .i18n import ui_text


class SettingsView(ttk.Frame):
    """ChatGPT-style Settings: category rail on the left, one-language content on the right."""

    def __init__(self, master, settings: Settings, on_save, security: SecurityManager | None = None, remote_status=None):
        super().__init__(master, padding=0)
        self.settings = settings
        self.on_save = on_save
        self.security = security
        self.remote_status = remote_status
        self.language = settings.interface_language
        self.vars: dict[str, tk.Variable] = {}
        self.entries: dict[str, ttk.Entry] = {}
        self.combo_maps: dict[str, dict[str, object]] = {}
        self.current = "general"
        self._build_shell()
        self.show_category("general")

    def t(self, ar, en): return ui_text(ar, en, self.language)

    def _build_shell(self):
        self.columnconfigure(1, weight=1); self.rowconfigure(0, weight=1)
        left = ttk.Frame(self, padding=(20, 22, 12, 20)); left.grid(row=0,column=0,sticky="ns")
        ttk.Label(left,text=self.t("الإعدادات","Settings"),style="Title.TLabel").pack(anchor="w",pady=(0,14))
        cats = [
            ("general",self.t("عام","General")), ("ai",self.t("Hammer والذكاء","AI & Hammer")),
            ("remote",self.t("Android وGitHub","Android & GitHub")),
            ("pairing",self.t("الإقران التلقائي QR","Automatic QR pairing")),
            ("desktop",self.t("التحكم بالكمبيوتر","Computer control")),
            ("facebook","Facebook"), ("backup",self.t("النسخ الاحتياطي","Backup")),
            ("security",self.t("الأمان والصلاحيات","Security & permissions")),
            ("notifications",self.t("التنبيهات","Notifications")), ("appearance",self.t("المظهر واللغة","Appearance & language")),
            ("voice",self.t("الصوت","Voice")), ("memory",self.t("الذاكرة والتعلم","Memory & learning")),
            ("advanced",self.t("متقدم","Advanced")),
        ]
        self.cat_buttons={}
        for key,label in cats:
            b=ttk.Button(left,text=label,command=lambda k=key:self.show_category(k));b.pack(fill="x",pady=2);self.cat_buttons[key]=b
        self.right=ttk.Frame(self,padding=(18,22,26,20));self.right.grid(row=0,column=1,sticky="nsew");self.right.columnconfigure(0,weight=1);self.right.rowconfigure(1,weight=1)
        self.header=ttk.Label(self.right,text="",style="Title.TLabel");self.header.grid(row=0,column=0,sticky="w",pady=(0,12))
        self.content=ttk.Frame(self.right);self.content.grid(row=1,column=0,sticky="nsew");self.content.columnconfigure(0,weight=1)
        footer=ttk.Frame(self.right);footer.grid(row=2,column=0,sticky="ew",pady=(14,0))
        ttk.Button(footer,text=self.t("حفظ وتطبيق","Save & apply"),style="Accent.TButton",command=self.save).pack(side="right")
        self.status=ttk.Label(footer,text="",style="Muted.TLabel");self.status.pack(side="left")

    def _clear(self):
        for w in self.content.winfo_children():w.destroy()
        self.vars={}; self.entries={}; self.combo_maps={}

    def _bool(self,name,value):v=tk.BooleanVar(value=bool(value));self.vars[name]=v;return v
    def _str(self,name,value):v=tk.StringVar(value=str(value));self.vars[name]=v;return v
    def _int(self,name,value):v=tk.IntVar(value=int(value));self.vars[name]=v;return v

    def _section(self,title,subtitle=""):
        box=ttk.LabelFrame(self.content,text=title,padding=14);box.pack(fill="x",pady=(0,12));box.columnconfigure(1,weight=1)
        if subtitle:ttk.Label(box,text=subtitle,style="Muted.TLabel",wraplength=760).grid(row=0,column=0,columnspan=2,sticky="w",pady=(0,10))
        return box

    def _choice_label(self, value):
        if not isinstance(value, str): return str(value)
        labels = {
            "home": ("الرئيسية","Home"), "chat": ("المحادثة","Chat"), "last": ("آخر صفحة","Last page"),
            "tray": ("شريط النظام","System tray"), "exit": ("إغلاق كامل","Exit"), "ask": ("اسألني كل مرة","Ask every time"),
            "off": ("متوقف","Off"), "window": ("فتح النافذة","Open window"),
            "formal": ("رسمي","Formal"), "friendly": ("ودود","Friendly"), "playful": ("خفيف ومرح","Playful"), "custom": ("مخصص","Custom"),
            "eco": ("اقتصادي","Eco"), "balanced": ("متوازن","Balanced"), "performance": ("أداء أعلى","Performance"),
            "auto": ("تلقائي","Automatic"), "default": ("متصفح Windows الافتراضي","Windows default browser"), "custom": ("مخصص","Custom"),
            "extension_first": ("المتصفح المفتوح أولاً","Open browser first"), "managed_profile": ("ملف متصفح مُدار","Managed browser profile"),
            "every_launch": ("كل مرة يفتح البرنامج","Every app launch"), "windows_session": ("مرة بعد تشغيل Windows","Once per Windows session"), "none": ("بدون كلمة مرور","No password"),
            "always": ("دائمًا","Always"), "threshold": ("حسب الحد","By threshold"),
            "system": ("حسب Windows","System"), "light": ("فاتح","Light"), "dark": ("داكن","Dark"),
            "message": ("نفس لغة رسالتي","Same as my message"), "interface": ("نفس لغة الواجهة","Same as interface"), "ar": ("العربية","Arabic"), "en": ("الإنجليزية","English"),
            "jordanian": ("أردني","Jordanian"), "msa": ("عربي فصيح","Modern Standard Arabic"), "gulf": ("خليجي","Gulf Arabic"), "egyptian": ("مصري","Egyptian"),
            "local": ("محلي","Local"), "cloud": ("سحابي","Cloud"), "voice_if_started": ("صوت إذا بدأت بالصوت","Voice if started by voice"), "text": ("نص فقط","Text only"),
            "soft_friendly": ("ناعم وودود","Soft & friendly"), "warm": ("دافئ","Warm"),
            "low": ("منخفض","Low"), "medium": ("متوسط","Medium"), "high": ("مرتفع","High"),
            "7d": ("7 أيام","7 days"), "30d": ("30 يوم","30 days"), "90d": ("90 يوم","90 days"), "forever": ("دائمًا","Forever"), "size": ("حسب الحجم","By size"),
        }
        pair=labels.get(value); return self.t(*pair) if pair else value

    def _row_combo(self,box,row,label,name,value,values,width=25):
        ttk.Label(box,text=label).grid(row=row,column=0,sticky="w",pady=6,padx=(0,12))
        if all(isinstance(x,str) for x in values):
            display=[self._choice_label(x) for x in values]; reverse={d:v for d,v in zip(display,values)}; self.combo_maps[name]=reverse
            v=self._str(name,self._choice_label(value)); c=ttk.Combobox(box,textvariable=v,state="readonly",values=display,width=width)
        else:
            v=self._str(name,value); c=ttk.Combobox(box,textvariable=v,state="readonly",values=[str(x) for x in values],width=width)
        c.grid(row=row,column=1,sticky="w",pady=6);return c
    def _row_entry(self,box,row,label,name,value,show=None,width=48):
        ttk.Label(box,text=label).grid(row=row,column=0,sticky="w",pady=6,padx=(0,12));v=self._str(name,value);e=ttk.Entry(box,textvariable=v,width=width,show=show);e.grid(row=row,column=1,sticky="ew",pady=6);self.entries[name]=e;return e
    def _row_check(self,box,row,label,name,value):
        v=self._bool(name,value);ttk.Checkbutton(box,text=label,variable=v).grid(row=row,column=0,columnspan=2,sticky="w",pady=6);return v

    def show_category(self,key):
        self.current=key;self._clear();titles={
            "general":self.t("عام","General"),"ai":self.t("Hammer والذكاء","AI & Hammer"),"facebook":"Facebook","backup":self.t("النسخ الاحتياطي","Backup"),
            "remote":self.t("Android وGitHub","Android & GitHub"),
            "pairing":self.t("الإقران التلقائي QR","Automatic QR pairing"),
            "desktop":self.t("التحكم بالكمبيوتر","Computer control"),
            "security":self.t("الأمان والصلاحيات","Security & permissions"),"notifications":self.t("التنبيهات","Notifications"),
            "appearance":self.t("المظهر واللغة","Appearance & language"),"voice":self.t("الصوت","Voice"),"memory":self.t("الذاكرة والتعلم","Memory & learning"),"advanced":self.t("متقدم","Advanced")}
        self.header.config(text=titles[key]);getattr(self,f"_page_{key}")()

    def _page_general(self):
        b=self._section(self.t("بدء التشغيل","Startup"))
        self._row_combo(b,1,self.t("صفحة البداية","Startup page"),"startup_page",self.settings.startup_page,["home","chat","last"])
        self._row_combo(b,2,self.t("عند الضغط على X","When closing X"),"close_behavior",self.settings.close_behavior,["tray","exit","ask"])
        self._row_combo(b,3,self.t("بدء مع Windows","Start with Windows"),"start_with_windows",self.settings.start_with_windows,["off","tray","window"])
        b2=self._section(self.t("هوية المساعد","Assistant identity"))
        self._row_entry(b2,1,self.t("اسم المساعد","Assistant name"),"assistant_name",self.settings.assistant_name)
        self._row_combo(b2,2,self.t("الشخصية","Personality"),"personality_style",self.settings.personality_style,["formal","friendly","playful","custom"])
        self._row_entry(b2,3,self.t("وصف مخصص للشخصية","Custom personality"),"personality_prompt",self.settings.personality_prompt)

    def _page_ai(self):
        b=self._section(self.t("العقل الرئيسي","Primary brain"),self.t("Hammer هو النموذج الوحيد للمحادثة وفهم الأوامر. لا يوجد موديل احتياطي مخفي.","Hammer is the only model for conversation and command understanding. No hidden fallback model."))
        ttk.Label(b,text=self.t("الموديل","Model")).grid(row=1,column=0,sticky="w",pady=6);ttk.Label(b,text=HAMMER_MODEL_LABEL,style="CardTitle.TLabel").grid(row=1,column=1,sticky="w")
        ttk.Label(b,text=self.t("الترخيص","License")).grid(row=2,column=0,sticky="w",pady=6);ttk.Label(b,text=f"{HAMMER_LICENSE} • {self.t('غير تجاري', 'non-commercial')}",style="Muted.TLabel").grid(row=2,column=1,sticky="w")
        self._row_combo(b,3,self.t("وضع الأداء","Performance mode"),"performance_mode",self.settings.performance_mode,["eco","balanced","performance"])
        self._row_combo(b,4,self.t("إخراج Hammer من RAM بعد","Unload after idle"),"hammer_idle_minutes",self.settings.hammer_idle_minutes,[0,5,15,30])
        self._row_combo(b,5,self.t("محاولات إعادة التشغيل","Automatic restart retries"),"hammer_retry_count",self.settings.hammer_retry_count,[0,1,2])
        p=self._section(self.t("إعدادات متقدمة للأداء","Advanced performance"))
        self._row_combo(p,1,"Context","context_tokens",self.settings.context_tokens,[768,1024,1536,2048])
        self._row_combo(p,2,"CPU threads","threads",self.settings.threads,[1,2])
        self._row_combo(p,3,self.t("حد الرد","Max reply tokens"),"max_response_tokens",self.settings.max_response_tokens,[96,128,160,220,256])
        self._row_combo(p,4,self.t("مهلة Hammer بالثواني","Hammer timeout seconds"),"ai_timeout_seconds",self.settings.ai_timeout_seconds,[45,60,90,120,150,180])

    def _page_remote(self):
        b=self._section(self.t("ربط تطبيق Android", "Connect the Android app"), self.t(
            "فعّل الاتصال وأنشئ مفتاح اقتران. للوصول من خارج البيت، شغّل Tailscale على الكمبيوتر والهاتف وفعّل Tailscale Serve للبرنامج. أدخل عنوان HTTPS ومفتاح الاقتران في تطبيق Android. يجب أن يبقى الكمبيوتر والبرنامج متصلين؛ لا يبدأ الاتصال قبل فتح قفل البرنامج.",
            "Enable the connection and generate a pairing token. For access away from home, run Tailscale on the computer and phone and expose this app with Tailscale Serve. Enter its HTTPS address and pairing token in the Android app. Keep this computer and app online. The connection starts after app unlock."))
        self._row_check(b,1,self.t("تفعيل اتصال Android", "Enable Android connection"),"remote_enabled",self.settings.remote_enabled)
        self._row_entry(b,2,self.t("منفذ الاتصال على الكمبيوتر", "Connection port on this computer"),"remote_port",self.settings.remote_port,width=12)
        pairing=ttk.Frame(b)
        pairing.grid(row=3,column=0,columnspan=2,sticky="ew",pady=5)
        ttk.Button(pairing,text=self.t("عرض ونسخ مفتاح الاقتران", "Show and copy pairing token"),command=self._show_pairing_token).pack(side="left",padx=(0,6))
        ttk.Button(pairing,text=self.t("إنشاء / تغيير المفتاح", "Generate / replace token"),command=self._regenerate_pairing_token).pack(side="left")
        self._remote_status_label=ttk.Label(b,text="",style="Muted.TLabel",wraplength=690)
        self._remote_status_label.grid(row=4,column=0,columnspan=2,sticky="w",pady=3)
        ttk.Button(b,text=self.t("تحديث حالة الاتصال", "Refresh connection status"),command=self._refresh_remote_status).grid(row=5,column=0,columnspan=2,sticky="w",pady=3)
        self._refresh_remote_status()
        g=self._section("GitHub",self.t("اختر نسخة Git المحلية مرة واحدة. ستُستخدم في المحادثات الجديدة وعلى الهاتف. يجب إعداد تسجيل الدخول إلى Git على هذا الكمبيوتر.", "Select the local Git checkout once. New chats and phone requests reuse it. Configure command-line Git authentication on this computer."))
        self._row_entry(g,1,self.t("المستودع: owner/name", "Repository: owner/name"),"github_repository",self.settings.github_repository)
        self._row_entry(g,2,self.t("مجلد المستودع المحلي", "Local checkout folder"),"github_checkout",self.settings.github_checkout)
        ttk.Button(g,text=self.t("اختيار المجلد", "Choose folder"),command=self._choose_github_checkout).grid(row=3,column=1,sticky="w",pady=5)

    def _page_pairing(self):
        b=self._section(self.t("ربط تلقائي بدون VPN", "Automatic connection without a VPN"),self.t(
            "بعد تجهيز استضافة الخادم مرة واحدة، احفظ عنوانه ومفتاح تسجيله هنا. بعدها يكفي مسح QR بالهاتف؛ الاتصال يعيد نفسه تلقائياً طالما الكمبيوتر والبرنامج شغّالان. مفتاح تسجيل الخادم لا يصل إلى الهاتف.",
            "After deploying the relay once, save its URL and enrollment key here. The phone then pairs by scanning QR and reconnects automatically. The server enrollment key is never sent to the phone."))
        ttk.Button(b,text=self.t("استيراد ملف إعداد الخادم", "Import server setup file"),command=self._import_relay_setup).grid(row=8,column=0,columnspan=2,sticky='e',pady=8)
        self._row_entry(b,1,self.t("عنوان HTTPS للخادم", "Relay HTTPS address"),"remote_relay_url",self.settings.remote_relay_url)
        self._row_entry(b,2,self.t("مفتاح تسجيل الخادم — فارغ للإبقاء", "Server enrollment key — blank keeps it"),"relay_enrollment_input","",show='•')
        ttk.Button(b,text=self.t("تفعيل وحفظ الاتصال التلقائي", "Enable and save automatic connection"),command=self._save_pairing).grid(row=3,column=0,columnspan=2,sticky='w',pady=8)
        ttk.Button(b,text=self.t("عرض QR لإقران الهاتف", "Show phone pairing QR"),command=self._show_pairing_qr).grid(row=4,column=0,columnspan=2,sticky='w',pady=8)
        ttk.Label(b,text=self.t("امسح الرمز من تطبيق الهاتف. الرمز يمنح الوصول لجهازك؛ تغيير مفتاح الاقتران من Android وGitHub يلغي وصول الهواتف القديمة.",
                               "Scan using the phone app. The QR grants device access; rotating the pairing key under Android & GitHub revokes old phones."),wraplength=650).grid(row=5,column=0,columnspan=2,sticky='w')
        self._remote_status_label=ttk.Label(b,text='',wraplength=650)
        self._remote_status_label.grid(row=6,column=0,columnspan=2,sticky='w',pady=8)
        ttk.Button(b,text=self.t("تحديث الحالة", "Refresh status"),command=self._refresh_remote_status).grid(row=7,column=0,sticky='w')
        self._refresh_remote_status()

    def _import_relay_setup(self):
        import json
        try:
            name=filedialog.askopenfilename(parent=self,filetypes=[('Server setup','*.json')])
            if not name:return
            path=Path(name)
            if path.stat().st_size>4096:raise ValueError('Invalid setup file')
            data=json.loads(path.read_text(encoding='utf-8'))
            if set(data)!={'relay_url','enrollment_key'} or any(not isinstance(value,str) for value in data.values()):raise ValueError('Invalid setup file')
            self.vars['remote_relay_url'].set(data['relay_url'])
            self.vars['relay_enrollment_input'].set(data['enrollment_key'])
            self._save_pairing()
        except Exception:self.status.configure(text=self.t('تعذر استيراد ملف إعداد الخادم.','Could not import server setup file.'))

    def _save_pairing(self):
        from ..remote.settings import save_relay_enrollment,load_relay_enrollment,load_remote_token,generate_remote_token
        from ..remote.relay_protocol import origin
        try:
            if not self.security or not self.security.unlocked:raise ValueError(self.t('افتح قفل البرنامج أولاً.','Unlock the app first.'))
            updated=replace(self.settings)
            updated.remote_relay_url=origin(self._value('remote_relay_url',self.settings.remote_relay_url))
            enrollment=str(self._value('relay_enrollment_input','')).strip()
            if enrollment:save_relay_enrollment(self.security,enrollment)
            if not load_relay_enrollment(self.security):raise ValueError(self.t('أدخل مفتاح تسجيل الخادم أولاً.','Enter the relay enrollment key first.'))
            if not load_remote_token(self.security):generate_remote_token(self.security)
            updated.remote_enabled=True;updated.remote_connection_mode='relay'
            updated.save();self.settings=updated;self.on_save(updated)
            if 'relay_enrollment_input' in self.vars:self.vars['relay_enrollment_input'].set('')
            self.status.configure(text=self.t('تم الحفظ؛ اتصال الخادم في الخلفية.','Saved; connecting to relay in background.'));self._refresh_remote_status()
        except (ValueError,OSError,SecurityError) as exc:self.status.configure(text=str(exc))

    def _show_pairing_qr(self):
        from ..remote.settings import pairing_payload,load_remote_token
        try:
            if not self.security or not self.security.unlocked:raise ValueError(self.t('افتح قفل البرنامج أولاً.','Unlock the app first.'))
            if self.settings.remote_connection_mode!='relay':raise ValueError(self.t('احفظ إعداد الخادم أولاً.','Save relay configuration first.'))
            payload=pairing_payload(self.settings.remote_relay_url,load_remote_token(self.security))
            import qrcode
            from PIL import ImageTk
            image=qrcode.make(payload).convert('RGB');image.thumbnail((450,450))
            dialog=tk.Toplevel(self);dialog.title(self.t('اقتران الهاتف','Pair phone'))
            photo=ImageTk.PhotoImage(image,master=dialog)
            label=ttk.Label(dialog,image=photo);label.image=photo;label.pack(padx=20,pady=15)
            ttk.Label(dialog,text=self.t('افتح تطبيق Android واضغط مسح QR. احتفظ بهذا الرمز لنفسك.','Open Android and tap Scan QR. Keep this code private.'),wraplength=440).pack(padx=15,pady=10)
        except Exception as exc:self.status.configure(text=str(exc) if isinstance(exc,(ValueError,SecurityError)) else self.t('تعذر عرض رمز الاقتران.','Could not show pairing QR.'))

    def _page_desktop(self):
        b=self._section(self.t("التحكم بالكمبيوتر من الهاتف", "Control this computer from the phone"), self.t(
            "عند التفعيل يستطيع الهاتف المقترن عرض الشاشة الرئيسية والنقر والكتابة ونقل الملفات. التحكم يعمل داخل جلسة Windows المفتوحة. تعطيل هذا الخيار يوقف التحكم عند حفظ الإعدادات.",
            "The paired phone can view the primary screen, click, type and transfer files in the unlocked Windows session. Save with this option off to revoke desktop control."))
        self._row_check(b,1,self.t("تفعيل الشاشة والتحكم ونقل الملفات", "Enable screen, input and file transfers"),"remote_desktop_enabled",self.settings.remote_desktop_enabled)
        self._row_check(b,2,self.t("تفعيل مساعد الكمبيوتر بالعربي", "Enable the computer AI assistant"),"remote_ai_enabled",self.settings.remote_ai_enabled)
        ttk.Label(b,text=self.t("مساعد الكمبيوتر يرسل أسماء وعناصر النافذة المرئية إلى Groq لفهم الأوامر. لا يرسل صور الشاشة أو محتوى الملفات. يطلب موافقة على المهمة قبل تنفيذ خطواتها.",
                               "Computer AI sends visible window labels/elements to Groq. It does not send screenshots or file contents. Approve the task before its steps execute."),wraplength=650).grid(row=3,column=0,columnspan=2,sticky="w",pady=8)
        f=self._section(self.t("مجلد الملفات المتاح للهاتف", "Phone file area"),self.t("الافتراضي هو مجلد المستخدم. اختر مجلداً أو قرصاً آخر إذا أردت إتاحته للهاتف. رفع ملف بنفس اسم ملف موجود يُرفض.",
                                                                                  "Defaults to your home folder. Choose another folder or drive to expose it to the phone. Uploads never overwrite existing files."))
        self._row_entry(f,1,self.t("المجلد", "Folder"),"remote_files_root",self.settings.remote_files_root)
        def choose():
            folder=filedialog.askdirectory(parent=self,mustexist=True)
            if folder:self.vars['remote_files_root'].set(folder)
        ttk.Button(f,text=self.t("اختيار المجلد أو القرص", "Choose folder or drive"),command=choose).grid(row=2,column=1,sticky='w')

    def _refresh_remote_status(self):
        label=getattr(self,"_remote_status_label",None)
        if label is not None:
            text=self.remote_status() if self.remote_status else self.t("احفظ الإعدادات لتطبيق الاتصال.", "Save settings to apply the connection.")
            label.configure(text=text)

    def _choose_github_checkout(self):
        selected=filedialog.askdirectory(parent=self,title=self.t("اختر مجلد نسخة Git المحلية", "Choose a local Git checkout"),mustexist=True)
        if selected:self.vars["github_checkout"].set(selected)

    def _show_pairing_token(self):
        from ..remote.settings import load_remote_token
        try:
            if not self.security or not self.security.unlocked:
                raise SecurityError(self.t("افتح قفل البرنامج أولاً.", "Unlock the app first."))
            token=load_remote_token(self.security)
            if not token:
                raise SecurityError(self.t("أنشئ مفتاح اقتران أولاً.", "Generate a pairing token first."))
            dlg=tk.Toplevel(self)
            dlg.title(self.t("مفتاح اقتران Android", "Android pairing token"))
            dlg.transient(self)
            body=ttk.Frame(dlg,padding=20)
            body.pack(fill="both",expand=True)
            ttk.Label(body,text=self.t("أدخل هذا المفتاح في تطبيق Android على هاتفك.", "Enter this token in the Android app on your phone.")).pack(anchor="w",pady=(0,10))
            entry=ttk.Entry(body,width=56)
            entry.insert(0,token)
            entry.configure(state="readonly")
            entry.pack(fill="x",pady=4)
            def copy():
                self.clipboard_clear()
                self.clipboard_append(token)
            ttk.Button(body,text=self.t("نسخ", "Copy"),command=copy).pack(anchor="e",pady=8)
        except (OSError,SecurityError) as exc:
            self.status.configure(text=str(exc))

    def _regenerate_pairing_token(self):
        from ..remote.settings import generate_remote_token, TOKEN_FILE
        try:
            if not self.security or not self.security.unlocked:
                raise SecurityError(self.t("افتح قفل البرنامج أولاً.", "Unlock the app first."))
            exists=(Path(self.security.root)/TOKEN_FILE).exists()
            if exists and not messagebox.askyesno(self.t("تغيير مفتاح الاقتران", "Replace pairing token"),self.t(
                    "سيُلغى اتصال الهواتف المقترنة بالمفتاح القديم. هل تريد إنشاء مفتاح جديد؟",
                    "Phones paired with the old token will lose access. Generate a new token?"),parent=self):
                return
            generate_remote_token(self.security)
            # Restart immediately so an old token cannot authorize new requests.
            self.on_save(self.settings)
            self._refresh_remote_status()
            self._show_pairing_token()
        except (OSError,SecurityError) as exc:
            self.status.configure(text=str(exc))

    def _page_facebook(self):
        b=self._section("Facebook",self.t("يبدأ بفحص حالة خفيف في الخلفية. المتصفح المفتوح العادي هو الخيار المفضل عبر Browser Bridge، مع fallback للملف المُدار.","A light status check runs in the background. The normal open browser is preferred through Browser Bridge, with managed-profile fallback."))
        self._row_entry(b,1,self.t("صفحة المصدر الافتراضية","Default source page"),"default_source_page",self.settings.default_source_page)
        self._row_check(b,2,self.t("فحص الاتصال تلقائيًا عند فتح البرنامج","Check connection automatically at startup"),"facebook_auto_check",self.settings.facebook_auto_check)
        self._row_combo(b,3,self.t("المتصفح","Browser"),"facebook_browser_choice",self.settings.facebook_browser_choice,["auto","default","edge","chrome","firefox","custom"])
        self._row_entry(b,4,self.t("مسار متصفح مخصص","Custom browser path"),"facebook_browser_custom_path",self.settings.facebook_browser_custom_path)
        self._row_combo(b,5,self.t("طريقة التحكم","Control mode"),"facebook_browser_mode",self.settings.facebook_browser_mode,["extension_first","managed_profile"])
        limits=self._section(self.t("حدود النشر","Publishing limits"))
        self._row_combo(limits,1,self.t("أقل فاصل بالثواني","Minimum delay seconds"),"facebook_interval_min_seconds",self.settings.facebook_interval_min_seconds,[30,45,50,60,90])
        self._row_combo(limits,2,self.t("أعلى فاصل بالثواني","Maximum delay seconds"),"facebook_interval_max_seconds",self.settings.facebook_interval_max_seconds,[60,90,120,180])
        self._row_entry(limits,3,self.t("حد الساعة","Hourly limit"),"facebook_hourly_limit",self.settings.facebook_hourly_limit,width=12)
        self._row_entry(limits,4,self.t("حد اليوم","Daily limit"),"facebook_daily_limit",self.settings.facebook_daily_limit,width=12)
        self._row_entry(limits,5,self.t("منع تكرار بالأيام","No-repeat days"),"facebook_no_repeat_days",self.settings.facebook_no_repeat_days,width=12)

    def _page_backup(self):
        b=self._section("Google Drive",self.t("النسخ مشفرة قبل الرفع. الربط يستخدم OAuth الرسمي ويتطلب Client ID حقيقي لتطبيق Desktop.","Backups are encrypted before upload. Connection uses official OAuth and requires a real Desktop app Client ID."))
        self._row_check(b,1,self.t("تفعيل مزامنة Drive","Enable Drive sync"),"drive_sync_enabled",self.settings.drive_sync_enabled)
        self._row_entry(b,2,"OAuth Client ID","google_drive_client_id",self.settings.google_drive_client_id)
        self._row_entry(b,3,self.t("OAuth Client Secret (اختياري لتطبيق Desktop)","OAuth Client Secret (optional for Desktop app)"),"google_drive_client_secret",self.settings.google_drive_client_secret,show="•")
        self._row_combo(b,4,self.t("فترة المزامنة بالدقائق","Sync interval minutes"),"drive_sync_interval_minutes",self.settings.drive_sync_interval_minutes,[15,30,60,180,360,1440])
        self._row_check(b,5,self.t("مزامنة الصور والمرفقات","Sync attachments"),"drive_sync_attachments",self.settings.drive_sync_attachments)
        cred=self._section(self.t("بيانات الدخول","Credentials"),self.t("الافتراضي: لا تتم مزامنة الأسرار. فعّل كل خدمة بشكل مستقل إذا أردت.","Default: secrets are not synced. Enable each service explicitly if desired."))
        self._row_check(cred,1,"Facebook","sync_facebook_credentials",self.settings.sync_facebook_credentials)
        self._row_check(cred,2,"Telegram","sync_telegram_credentials",self.settings.sync_telegram_credentials)
        self._row_check(cred,3,"GitHub","sync_github_credentials",self.settings.sync_github_credentials)

    def _page_security(self):
        b=self._section(self.t("قفل البرنامج","App lock"))
        self._row_combo(b,1,self.t("طلب كلمة المرور","Password prompt"),"password_mode",self.settings.password_mode,["every_launch","windows_session","none"])
        ttk.Button(b,text=self.t("تغيير كلمة المرور / طريقة القفل","Change password / lock mode"),command=self._change_security).grid(row=2,column=0,columnspan=2,sticky="w",pady=8)
        ap=self._section(self.t("الموافقات","Approvals"))
        self._row_combo(ap,1,self.t("سياسة الموافقات","Approval policy"),"confirmation_policy",self.settings.confirmation_policy,["always","threshold","auto"])
        self._row_entry(ap,2,self.t("اطلب إذا عدد الجروبات أكبر من","Ask above group count"),"confirmation_group_threshold",self.settings.confirmation_group_threshold,width=12)
        self._row_combo(ap,3,self.t("انتهاء الموافقة بالدقائق","Approval timeout minutes"),"approval_timeout_minutes",self.settings.approval_timeout_minutes,[5,15,30,60,1440])
        ttk.Label(ap,text=self.t("تغييرات الأمان، كلمات المرور، والحذف الكبير تبقى محمية حتى لو كانت الموافقات العادية تلقائية.","Security changes, passwords and destructive bulk actions remain protected even if normal approvals are automatic."),style="Muted.TLabel",wraplength=720).grid(row=4,column=0,columnspan=2,sticky="w",pady=(8,0))

    def _page_notifications(self):
        b=self._section(self.t("طرق التنبيه","Notification channels"))
        self._row_check(b,1,self.t("داخل البرنامج","In app"),"notify_in_app",self.settings.notify_in_app)
        self._row_check(b,2,self.t("إشعار Windows","Windows notification"),"notify_windows",self.settings.notify_windows)
        self._row_check(b,3,"Telegram","notify_telegram",self.settings.notify_telegram)

    def _page_appearance(self):
        b=self._section(self.t("اللغة والمظهر","Language & appearance"))
        self._row_combo(b,1,self.t("لغة الواجهة","Interface language"),"interface_language",self.settings.interface_language,["ar","en"])
        self._row_combo(b,2,self.t("المظهر","Appearance"),"appearance",self.settings.appearance,["system","light","dark"])
        self._row_combo(b,3,self.t("لغة رد Hammer","Hammer reply language"),"reply_language",self.settings.reply_language,["message","interface","ar","en"])
        self._row_combo(b,4,self.t("اللهجة العربية","Arabic dialect"),"arabic_dialect",self.settings.arabic_dialect,["jordanian","msa","gulf","egyptian","auto"])

    def _page_voice(self):
        b=self._section(self.t("الصوت","Voice"),self.t("الواجهة جاهزة للصوت المحلي/السحابي. محرك التعرف المحلي نفسه يُحمّل كمهارة اختيارية حتى لا يثقل جهاز 4GB.","The UI is ready for local/cloud voice. The local speech-recognition engine is an optional skill so it does not burden a 4 GB PC."))
        self._row_check(b,1,self.t("تفعيل الصوت","Enable voice"),"voice_enabled",self.settings.voice_enabled)
        self._row_combo(b,2,self.t("المعالجة","Backend"),"voice_backend",self.settings.voice_backend,["local","cloud"])
        self._row_combo(b,3,self.t("الرد الصوتي","Voice reply"),"voice_reply_mode",self.settings.voice_reply_mode,["always","voice_if_started","text"])
        self._row_check(b,4,self.t("تفعيل كلمة التنبيه","Enable wake word"),"wake_word_enabled",self.settings.wake_word_enabled)
        self._row_entry(b,5,self.t("كلمة التنبيه","Wake word"),"wake_word",self.settings.wake_word)
        self._row_combo(b,6,self.t("أسلوب الصوت","Voice style"),"voice_style",self.settings.voice_style,["soft_friendly","warm","playful","formal"])
        self._row_entry(b,7,self.t("السرعة %","Speed %"),"voice_rate",self.settings.voice_rate,width=10)
        self._row_entry(b,8,self.t("النبرة %","Pitch %"),"voice_pitch",self.settings.voice_pitch,width=10)
        self._row_entry(b,9,self.t("مستوى الصوت %","Volume %"),"voice_volume",self.settings.voice_volume,width=10)

    def _page_memory(self):
        b=self._section(self.t("الذاكرة والتعلم","Memory & learning"))
        self._row_check(b,1,self.t("السماح بتعلم تفضيلاتي وأنماط الشغل","Learn my preferences and work patterns"),"learning_enabled",self.settings.learning_enabled)
        self._row_combo(b,2,self.t("مستوى الاقتراحات","Suggestion level"),"suggestion_level",self.settings.suggestion_level,["off","low","medium","high"])
        self._row_combo(b,3,self.t("الاحتفاظ بسجل النشاط","Audit log retention"),"audit_retention",self.settings.audit_retention,["7d","30d","90d","forever","size"])
        ttk.Label(b,text=self.t("المحادثات الخاصة وخيار «لا تحفظ هذا» يتم التحكم به من كل محادثة.","Private chats and “do not remember this” are controlled per conversation."),style="Muted.TLabel",wraplength=720).grid(row=4,column=0,columnspan=2,sticky="w",pady=(8,0))

    def _page_advanced(self):
        b=self._section(self.t("التكاملات المتقدمة","Advanced integrations"))
        ttk.Button(b,text=self.t("إعداد Android وGitHub", "Configure Android & GitHub"),command=lambda:self.show_category("remote")).grid(row=1,column=0,columnspan=2,sticky="w",pady=6)
        self._row_check(b,2,"GitHub","github_enabled",self.settings.github_enabled)
        self._row_check(b,3,self.t("نظام Skills","Skills system"),"skills_enabled",self.settings.skills_enabled)
        self._row_check(b,4,self.t("السماح بمهارات GitHub بعد الموافقة","Allow GitHub skills after approval"),"allow_github_skills",self.settings.allow_github_skills)
        self._row_check(b,5,self.t("السماح بمهارات محلية","Allow local skills"),"allow_local_skills",self.settings.allow_local_skills)
        ttk.Label(b,text=self.t("المهارات غير الموثوقة يجب أن تعمل بعزل قدر الإمكان ولا تُمنح صلاحيات تلقائيًا.","Untrusted skills should run isolated where possible and never receive permissions automatically."),style="Muted.TLabel",wraplength=720).grid(row=6,column=0,columnspan=2,sticky="w",pady=(8,0))

    def _change_security(self):
        if not self.security:
            return
        dlg=tk.Toplevel(self);dlg.title(self.t("تغيير الأمان","Change security"));dlg.geometry("500x360");dlg.transient(self);dlg.grab_set()
        f=ttk.Frame(dlg,padding=22);f.pack(fill="both",expand=True)
        ttk.Label(f,text=self.t("تغيير كلمة المرور وطريقة القفل","Change password and lock mode"),style="Title.TLabel").pack(anchor="w",pady=(0,12))
        ttk.Label(f,text=self.t("أدخل كلمة المرور الحالية أو مفتاح الاسترداد أولًا.","Enter the current password or recovery key first."),style="Muted.TLabel").pack(anchor="w",pady=(0,12))
        old=ttk.Entry(f,show="•");old.pack(fill="x",pady=4)
        use_recovery=tk.BooleanVar(value=False);ttk.Checkbutton(f,text=self.t("القيمة أعلاه هي Recovery Key","The value above is a Recovery Key"),variable=use_recovery).pack(anchor="w",pady=4)
        mode_values=["every_launch","windows_session","none"]
        mode_display=[self._choice_label(v) for v in mode_values]
        mode_reverse={label:value for label,value in zip(mode_display,mode_values)}
        mode=tk.StringVar(value=self._choice_label(self.settings.password_mode));ttk.Combobox(f,textvariable=mode,state="readonly",values=mode_display).pack(fill="x",pady=6)
        new=ttk.Entry(f,show="•");new.pack(fill="x",pady=4)
        confirm=ttk.Entry(f,show="•");confirm.pack(fill="x",pady=4)
        status=ttk.Label(f,text="",style="Muted.TLabel");status.pack(anchor="w",pady=8)
        def apply_change():
            try:
                if use_recovery.get():self.security.unlock_with_recovery(old.get().strip())
                elif self.security.mode()=="none":self.security.unlock_without_password()
                else:self.security.unlock_with_password(old.get())
                selected_mode=mode_reverse.get(mode.get(), self.settings.password_mode)
                if selected_mode!="none" and new.get()!=confirm.get():raise SecurityError(self.t("كلمتا المرور غير متطابقتين","Passwords do not match"))
                self.security.change_password(new.get() if selected_mode!="none" else "",selected_mode)
                self.settings.password_mode=selected_mode;self.settings.save();dlg.destroy();messagebox.showinfo(self.t("تم","Done"),self.t("تم تحديث إعدادات الأمان.","Security settings updated."),parent=self)
            except Exception as exc:status.config(text=str(exc))
        ttk.Button(f,text=self.t("حفظ","Save"),style="Accent.TButton",command=apply_change).pack(anchor="e",pady=6)

    def _value(self,name,default=None):
        v=self.vars.get(name);return v.get() if v is not None else default

    def save(self):
        if self.current == "pairing":return self._save_pairing()
        if self.current == "desktop":
            try:
                updated=replace(self.settings)
                updated.remote_desktop_enabled=bool(self._value('remote_desktop_enabled',False))
                updated.remote_ai_enabled=bool(self._value('remote_ai_enabled',False)) and updated.remote_desktop_enabled
                folder=str(self._value('remote_files_root','')).strip()
                if folder and not Path(folder).expanduser().is_dir():raise ValueError(self.t('مجلد الملفات غير موجود.','File folder does not exist.'))
                updated.remote_files_root=str(Path(folder).expanduser().resolve()) if folder else ''
                updated.save();self.settings=updated;self.on_save(updated)
                self.status.configure(text=self.t('تم الحفظ','Saved'))
            except (OSError,ValueError) as exc:self.status.configure(text=str(exc))
            return
        if self.current == "remote":
            return self._save_remote_settings()
        # Only fields currently rendered are changed; other settings stay intact.
        for name,var in self.vars.items():
            if not hasattr(self.settings,name):continue
            value=var.get()
            if name in self.combo_maps:value=self.combo_maps[name].get(str(value),value)
            current=getattr(self.settings,name)
            try:
                if isinstance(current,bool):value=bool(value)
                elif isinstance(current,int):value=int(value)
                else:value=str(value)
            except Exception:continue
            setattr(self.settings,name,value)
        # Keep security mode authoritative in SecurityManager; direct combobox change is advisory until changed through dialog.
        if self.security and self.security.configured:
            self.settings.password_mode=self.security.mode()
        self.settings.save();self.on_save(self.settings);self.status.config(text=self.t("تم الحفظ","Saved"))

    def _save_remote_settings(self):
        from ..github_upload_v430 import GitHubUploadError, validate_repository
        from ..remote.settings import load_remote_token
        try:
            updated=replace(self.settings)
            updated.remote_enabled=bool(self._value("remote_enabled",False))
            updated.remote_port=int(self._value("remote_port",8766))
            if not 1024 <= updated.remote_port <= 65535:
                raise ValueError(self.t("اختر منفذاً بين 1024 و65535.", "Choose a port between 1024 and 65535."))
            updated.github_repository=validate_repository(str(self._value("github_repository",self.settings.github_repository)))
            checkout=str(self._value("github_checkout","")).strip()
            if checkout:
                path=Path(checkout).expanduser()
                if not path.is_dir():raise ValueError(self.t("مجلد المستودع غير موجود.", "The checkout folder does not exist."))
                updated.github_checkout=str(path.resolve())
            else:
                updated.github_checkout=""
            if updated.remote_enabled:
                if not self.security or not self.security.unlocked:
                    raise ValueError(self.t("افتح قفل البرنامج قبل إعداد الاتصال.", "Unlock the app before configuring the connection."))
                if not load_remote_token(self.security):
                    raise ValueError(self.t("أنشئ مفتاح اقتران أولاً.", "Generate a pairing token first."))
            updated.save()
            self.settings=updated
            self.on_save(updated)
            self.status.configure(text=self.t("تم الحفظ", "Saved"))
            self._refresh_remote_status()
        except (ValueError, OSError, SecurityError, GitHubUploadError) as exc:
            self.status.configure(text=str(exc))
