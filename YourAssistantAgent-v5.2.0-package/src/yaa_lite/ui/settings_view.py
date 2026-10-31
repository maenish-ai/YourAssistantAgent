from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from dataclasses import replace
from pathlib import Path

from ..agent.hammer_agent import HAMMER_LICENSE, HAMMER_MODEL_LABEL
from ..config import Settings
from ..security.manager import SecurityManager, SecurityError
from .i18n import ui_text
from . import theme


class SettingsView(ttk.Frame):
    """ChatGPT-style Settings: category rail on the left, one-language content on the right."""

    def __init__(self, master, settings: Settings, on_save, security: SecurityManager | None = None, remote_status=None, remote_ready=None):
        super().__init__(master, padding=0)
        self.settings = settings
        self.on_save = on_save
        self.security = security
        self.remote_status = remote_status
        self.remote_ready = remote_ready
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
        self._status_after=None
        for key,label in cats:
            b=ttk.Button(left,text=label,style="Nav.TButton",command=lambda k=key:self.show_category(k));b.pack(fill="x",pady=2);self.cat_buttons[key]=b
        self.right=ttk.Frame(self,padding=(18,22,26,20));self.right.grid(row=0,column=1,sticky="nsew");self.right.columnconfigure(0,weight=1);self.right.rowconfigure(1,weight=1)
        self.header=ttk.Label(self.right,text="",style="Title.TLabel");self.header.grid(row=0,column=0,sticky="w",pady=(0,12))
        viewport=ttk.Frame(self.right);viewport.grid(row=1,column=0,sticky="nsew");viewport.columnconfigure(0,weight=1);viewport.rowconfigure(0,weight=1)
        self._canvas=tk.Canvas(viewport,bg=theme.BG,highlightthickness=0,width=420)
        self._canvas.grid(row=0,column=0,sticky="nsew")
        scrollbar=ttk.Scrollbar(viewport,orient="vertical",command=self._canvas.yview);scrollbar.grid(row=0,column=1,sticky="ns")
        self._canvas.configure(yscrollcommand=scrollbar.set)
        self.content=ttk.Frame(self._canvas);self.content.columnconfigure(0,weight=1)
        content_window=self._canvas.create_window((0,0),window=self.content,anchor="nw")
        self.content.bind("<Configure>",lambda e:self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        def fit_width(event):
            width=event if isinstance(event,int) else event.width
            self._canvas.itemconfigure(content_window,width=width)
            def wrap(parent):
                for child in parent.winfo_children():
                    if isinstance(child,ttk.Label) and int(child.cget('wraplength') or 0)>0:
                        child.configure(wraplength=max(180,width-48))
                    wrap(child)
            wrap(self.content)
        self._canvas.bind("<Configure>",fit_width)
        self._fit_settings_width=fit_width
        top=self.winfo_toplevel()
        self._wheel_id=top.bind("<MouseWheel>",self._scroll_settings,add="+")
        self.bind("<Destroy>",self._destroy_settings,add="+")
        footer=ttk.Frame(self.right);footer.grid(row=2,column=0,sticky="ew",pady=(14,0))
        ttk.Button(footer,text=self.t("حفظ وتطبيق","Save & apply"),style="Accent.TButton",command=self.save).pack(side="right")
        self.status=ttk.Label(footer,text="",style="Muted.TLabel");self.status.pack(side="left")

    def _scroll_settings(self,event):
        if str(event.widget).startswith(str(self)):
            self._canvas.yview_scroll(-int(event.delta/120) if abs(event.delta)>=120 else (-1 if event.delta>0 else 1),"units")

    def _destroy_settings(self,event):
        if event.widget is self:
            if self._status_after:self.after_cancel(self._status_after)
            if self._wheel_id:self.winfo_toplevel().unbind("<MouseWheel>",self._wheel_id)

    def _clear(self):
        if self._status_after:self.after_cancel(self._status_after);self._status_after=None
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

    def _stack_entry(self,box,row,label,name,value):
        ttk.Label(box,text=label,wraplength=500).grid(row=row,column=0,columnspan=2,sticky='w',pady=(8,3))
        variable=self._str(name,value);entry=ttk.Entry(box,textvariable=variable,width=24)
        entry.grid(row=row+1,column=0,columnspan=2,sticky='ew',pady=(0,6));self.entries[name]=entry
        return entry

    def show_category(self,key):
        self.current=key;self._clear();titles={
            "general":self.t("عام","General"),"ai":self.t("Hammer والذكاء","AI & Hammer"),"facebook":"Facebook","backup":self.t("النسخ الاحتياطي","Backup"),
            "remote":self.t("Android وGitHub","Android & GitHub"),
            "pairing":self.t("الإقران التلقائي QR","Automatic QR pairing"),
            "desktop":self.t("التحكم بالكمبيوتر","Computer control"),
            "security":self.t("الأمان والصلاحيات","Security & permissions"),"notifications":self.t("التنبيهات","Notifications"),
            "appearance":self.t("المظهر واللغة","Appearance & language"),"voice":self.t("الصوت","Voice"),"memory":self.t("الذاكرة والتعلم","Memory & learning"),"advanced":self.t("متقدم","Advanced")}
        self.header.config(text=titles[key])
        for name,button in self.cat_buttons.items():button.configure(style="ActiveNav.TButton" if name==key else "Nav.TButton")
        getattr(self,f"_page_{key}")();self._fit_settings_width(self._canvas.winfo_width());self._canvas.yview_moveto(0)

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
        self._pairing_page_mode="home"
        b=self._section(self.t("استضافة خاصة على هذا الكمبيوتر","Private hosting on this computer"),self.t(
            "اتصال HTTPS مباشر بين هاتفك والكمبيوتر. لا يلزم حساب استضافة أو تطبيق آخر. ابدأ داخل شبكة البيت، ثم جهّز الراوتر للوصول من الخارج.",
            "Direct HTTPS between your phone and computer. No hosting account or additional app. Start on home Wi-Fi, then configure your router for access from outside."))
        self._remote_status_label=ttk.Label(b,text='',style="CardTitle.TLabel",wraplength=510)
        self._remote_status_label.grid(row=1,column=0,columnspan=2,sticky='w',pady=8)
        self._qr_panel=ttk.Frame(b);self._qr_panel.grid(row=2,column=0,columnspan=2,sticky='ew')
        ttk.Label(self._qr_panel,text=self.t("اضغط تشغيل وعرض QR لإنشاء اتصال هذا الكمبيوتر.","Tap Start hosting and show QR to set up this computer."),wraplength=500).pack(anchor='w')
        ttk.Button(b,text=self.t("تشغيل وعرض QR","Start hosting and show QR"),style="Accent.TButton",command=self._save_home_pairing).grid(row=3,column=0,sticky='w',pady=8)
        ttk.Button(b,text=self.t("تفعيل التحكم الكامل وعرض QR","Enable full desktop access and show QR"),style="Accent.TButton",command=self._full_access_pairing).grid(row=4,column=0,columnspan=2,sticky='w',pady=6)
        ttk.Label(b,text=self.t("يشمل الشاشة والنقر والكتابة وكل الأقراص ومساعد الكمبيوتر. لا يشمل تجاوز قفل Windows أو UAC.","Includes screen, input, all local drives and computer AI. Does not bypass Windows lock or UAC."),wraplength=500,style='Muted.TLabel').grid(row=5,column=0,columnspan=2,sticky='w')
        permissions=self._section(self.t("١  •  شغّل الاستضافة واختر الصلاحيات","1  •  Start hosting and choose permissions"))
        self._row_check(permissions,1,self.t("الشاشة والنقر والكتابة ونقل الملفات","Screen, mouse, keyboard and file transfers"),'remote_desktop_enabled',self.settings.remote_desktop_enabled)
        self._row_check(permissions,2,self.t("مساعد الكمبيوتر — المحادثة والعناصر عبر Groq","Computer AI — uses Groq"),'remote_ai_enabled',self.settings.remote_ai_enabled)
        self._row_check(permissions,3,self.t("إتاحة كل الأقراص المحلية للهاتف","Expose all local drives to the phone"),'remote_files_all_drives',self.settings.remote_files_all_drives)
        self._row_check(permissions,4,self.t("منع السكون التلقائي أثناء توصيل الشاحن","Prevent idle sleep while connected to AC"),'remote_keep_awake',self.settings.remote_keep_awake)
        self._row_entry(permissions,5,self.t("منفذ HTTPS على الكمبيوتر","Computer HTTPS port"),'remote_home_port',self.settings.remote_home_port,width=10)
        self._str('remote_home_public_url',self.settings.remote_home_public_url)
        self._str('remote_home_lan_url',self.settings.remote_home_lan_url)
        ttk.Button(permissions,text=self.t("تشغيل الاستضافة على الكمبيوتر وعرض QR","Start hosting on this computer and show QR"),style="Accent.TButton",command=self._save_home_pairing).grid(row=6,column=0,columnspan=2,sticky='w',pady=10)
        network=self._section(self.t("٢  •  من خارج البيت — إعداد مرة واحدة","2  •  Away from home — one-time network setup"),self.t(
            "يلزم عنوان IPv4 عام مع توجيه منفذ TCP من الراوتر إلى الكمبيوتر، أو IPv6 عام مع سماح الجدار الناري. إذا كانت الشبكة خلف CGNAT ولا يوجد IPv6 متاح، فلن يعمل الوصول المباشر من الخارج ضمن هذه الشروط. QR لا يغيّر قيود الشبكة.",
            "Requires public IPv4 plus a TCP router port forward, or reachable public IPv6 with firewall permission. If your connection uses CGNAT and no reachable IPv6, direct access away from home is unavailable under these constraints. QR does not change network routing."))
        self._stack_entry(network,1,self.t("عنوان HTTPS العام — اختياري داخل البيت","Public HTTPS URL — optional on home Wi-Fi"),'remote_home_public_url',self.settings.remote_home_public_url)
        ttk.Label(network,text=self.t("مثال IPv4: https://PUBLIC-IP:8443  |  IPv6: https://[IPv6]:8443. استخدم عنوانك الحقيقي. تغيير العنوان يستلزم إعادة مسح QR.","IPv4 example: https://PUBLIC-IP:8443 | IPv6: https://[IPv6]:8443. Use your real address. Scan again if addresses change."),wraplength=500,style='Muted.TLabel').grid(row=3,column=0,columnspan=2,sticky='w',pady=6)
        self._stack_entry(network,4,self.t("عنوان محلي مخصص — فارغ للاكتشاف التلقائي","Custom LAN HTTPS URL — blank detects automatically"),'remote_home_lan_url',self.settings.remote_home_lan_url)
        helpbox=self._section(self.t("٣  •  امسح الرمز بهاتفك","3  •  Scan with your phone"),self.t(
            "اسمح للبرنامج في جدار Windows الناري، ثم افتح Android واضغط مسح QR وأنت على شبكة البيت. التطبيق يثبت هوية الكمبيوتر من الشهادة داخل الرمز، ويحاول العنوان المحلي ثم العام. يبقى الكمبيوتر مستيقظاً والبرنامج مفتوح القفل. الشاشة والملفات لا تمر بخادم خارجي؛ مساعد Groq له اتصال سحابي منفصل.",
            "Allow the app in Windows Firewall, then tap Scan QR on Android while on home Wi-Fi. The QR pins the computer certificate; the phone tries LAN and public addresses. Keep the computer awake and assistant unlocked. Screen and file data use no external relay; Groq AI uses its separate cloud connection."))
        ttk.Button(helpbox,text=self.t("إيقاف اتصال الهاتف","Disable phone access"),command=self._disable_phone).grid(row=1,column=0,sticky='w',pady=6)
        ttk.Button(helpbox,text=self.t("إلغاء اقتران الهواتف وتغيير المفتاح","Revoke paired phones and rotate key"),command=self._regenerate_pairing_token).grid(row=2,column=0,sticky='w',pady=6)
        ttk.Button(helpbox,text=self.t("إعداد الخادم الوسيط القديم — اختياري","Legacy relay configuration — optional"),command=self._show_relay_settings).grid(row=3,column=0,sticky='w',pady=6)
        self._refresh_remote_status();self._poll_pairing_status()
        if self.settings.remote_connection_mode=='home' and self.settings.remote_enabled:self._show_pairing_qr()

    def _show_relay_settings(self):
        self._clear();self._page_relay_pairing();self._fit_settings_width(self._canvas.winfo_width());self._canvas.yview_moveto(0)

    def _full_access_pairing(self):
        for name in ('remote_desktop_enabled','remote_ai_enabled','remote_files_all_drives','remote_keep_awake'):
            self.vars[name].set(True)
        self._save_home_pairing()

    def _save_home_pairing(self):
        from ..remote.home import endpoint,tls_context
        from ..remote.settings import load_remote_token,generate_remote_token
        try:
            if not self.security or not self.security.unlocked:raise ValueError(self.t('افتح قفل البرنامج أولاً.','Unlock the assistant first.'))
            updated=replace(self.settings)
            updated.remote_home_port=int(self._value('remote_home_port',8443))
            if not 1024<=updated.remote_home_port<=65535:raise ValueError(self.t('اختر منفذاً بين 1024 و65535.','Choose a port between 1024 and 65535.'))
            for name in ('remote_home_public_url','remote_home_lan_url'):
                value=str(self._value(name,'')).strip();setattr(updated,name,endpoint(value) if value else '')
            for name in ('remote_desktop_enabled','remote_ai_enabled','remote_files_all_drives','remote_keep_awake'):
                setattr(updated,name,bool(self._value(name,getattr(updated,name))))
            if updated.remote_ai_enabled and not updated.remote_desktop_enabled:raise ValueError(self.t('فعّل الشاشة والملفات لاستخدام مساعد الكمبيوتر.','Enable screen and files to use computer AI.'))
            tls_context(self.security)
            if not load_remote_token(self.security):generate_remote_token(self.security)
            updated.remote_connection_mode='home';updated.remote_enabled=True
            updated.save();self.settings=updated;self.on_save(updated)
            self._refresh_remote_status()
            if self._show_pairing_qr():self.status.configure(text=self.t('إعداد الراوتر مطلوب للوصول من الخارج؛ جرّب داخل البيت أولاً.','Router setup is required for access from outside; test on home Wi-Fi first.'))
        except (ValueError,OSError,SecurityError) as exc:self.status.configure(text=str(exc))

    def _page_relay_pairing(self):
        self._pairing_page_mode="relay"
        ttk.Button(self.content,text=self.t("العودة للاستضافة على هذا الكمبيوتر","Back to hosting on this computer"),command=lambda:self.show_category("pairing")).pack(anchor="w",pady=8)
        b=self._section(self.t("هاتفك. كمبيوترك. اتصال واحد.","Your phone. Your computer. Connected."),self.t(
            "الشاشة والملفات والمساعد في تطبيق واحد. جهّز الربط مرة واحدة، ثم امسح الرمز بهاتفك.",
            "Screen, files and assistant in one app. Set up the connection once, then scan with your phone."))
        self._remote_status_label=ttk.Label(b,text='',style="CardTitle.TLabel",wraplength=510)
        self._remote_status_label.grid(row=1,column=0,columnspan=2,sticky='w',pady=8)
        self._qr_panel=ttk.Frame(b);self._qr_panel.grid(row=2,column=0,columnspan=2,sticky='ew',pady=8)
        ttk.Label(self._qr_panel,text=self.t("QR يظهر هنا بعد استيراد إعداد الخادم.","Your QR appears here after importing server setup."),style="Muted.TLabel",wraplength=500).pack(anchor='w')
        ttk.Button(b,text=self.t("عرض QR وإقران الهاتف","Show pairing QR"),style="Accent.TButton",command=self._show_pairing_qr).grid(row=3,column=0,sticky='w',pady=8)
        ttk.Button(b,text=self.t("تحديث الحالة","Refresh status"),command=self._refresh_remote_status).grid(row=3,column=1,sticky='e')
        setup=self._section(self.t("١  •  إعداد الاتصال مرة واحدة","1  •  One-time connection setup"),self.t(
            "للوصول من خارج البيت يلزم خادم HTTPS منشور. لا يتوفر خادم عام تلقائياً مع تثبيت البرنامج. استورد ملف الإعداد الذي ينتج عن نشر خادمك.",
            "Access away from home requires a hosted HTTPS relay. Installing this app does not provision a public server. Import the setup file from your deployment."))
        ttk.Button(setup,text=self.t("استيراد ملف إعداد الخادم","Import server setup file"),style="Accent.TButton",command=self._import_relay_setup).grid(row=1,column=0,columnspan=2,sticky='w',pady=8)
        manual=ttk.Frame(setup)
        def toggle():
            if manual.winfo_manager():manual.grid_remove()
            else:manual.grid(row=3,column=0,columnspan=2,sticky='ew')
        ttk.Button(setup,text=self.t("إعداد الخادم يدوياً — متقدم","Manual server setup — advanced"),command=toggle).grid(row=2,column=0,columnspan=2,sticky='w')
        manual.columnconfigure(1,weight=1)
        self._row_entry(manual,1,self.t("عنوان HTTPS للخادم","Relay HTTPS address"),'remote_relay_url',self.settings.remote_relay_url,width=32)
        self._row_entry(manual,2,self.t("مفتاح تسجيل الخادم","Server enrollment key"),'relay_enrollment_input','',show='•',width=32)
        permissions=self._section(self.t("٢  •  صلاحيات هاتفك","2  •  Phone permissions"),self.t(
            "الرمز يسمح لهاتفك باستخدام الصلاحيات المحددة هنا. تغيير مفتاح الاقتران يلغي وصول الهواتف القديمة.",
            "The QR grants your phone the permissions selected here. Rotating the pairing key revokes previously paired phones."))
        self._row_check(permissions,1,self.t("الشاشة والنقر والكتابة ونقل الملفات","Screen, mouse, keyboard and file transfers"),'remote_desktop_enabled',self.settings.remote_desktop_enabled)
        self._row_check(permissions,2,self.t("مساعد الكمبيوتر الذكي — بموافقة على المهمة","Computer AI — task approval required"),'remote_ai_enabled',self.settings.remote_ai_enabled)
        self._row_check(permissions,3,self.t("إتاحة كل الأقراص المحلية للهاتف","Expose all local drives to the phone"),'remote_files_all_drives',self.settings.remote_files_all_drives)
        self._row_check(permissions,4,self.t("منع السكون التلقائي أثناء الربط وعلى الشاحن", "Prevent idle sleep while connected to AC"),'remote_keep_awake',self.settings.remote_keep_awake)
        ttk.Button(permissions,text=self.t("حفظ الصلاحيات وتفعيل الربط وعرض QR","Save permissions, enable connection and show QR"),style="Accent.TButton",command=lambda:self._save_pairing(show_qr=True)).grid(row=5,column=0,columnspan=2,sticky='w',pady=8)
        helpbox=self._section(self.t("٣  •  افتح التطبيق على هاتفك","3  •  Open the phone app"),self.t(
            "اضغط مسح QR في Android ووجّه الكاميرا إلى الرمز أعلاه. يُحفظ الاقتران ويُعاد الاتصال أثناء فتح التطبيق. الكمبيوتر يجب أن يبقى مستيقظاً والبرنامج مفتوح القفل. التحكم داخل جلسة Windows الحالية؛ شاشة القفل وUAC غير متاحتين.",
            "Tap Scan QR on Android and point the camera at the code above. Pairing is saved; reconnection runs while the phone app is open. Keep the computer awake and the assistant unlocked. Windows lock screens and UAC remain unavailable."))
        ttk.Button(helpbox,text=self.t("إلغاء اقتران الهواتف وتغيير المفتاح","Revoke paired phones and rotate key"),command=self._regenerate_pairing_token).grid(row=1,column=0,sticky='w',pady=5)
        ttk.Button(helpbox,text=self.t("إيقاف اتصال الهاتف على هذا الكمبيوتر","Disable phone access on this computer"),command=self._disable_phone).grid(row=2,column=0,sticky='w',pady=5)
        self._refresh_remote_status();self._poll_pairing_status()
        if self.settings.remote_connection_mode=='relay' and self.settings.remote_relay_url:self._show_pairing_qr()

    def _poll_pairing_status(self):
        self._status_after=None
        if self.current=='pairing' and self.winfo_exists():
            self._refresh_remote_status();self._status_after=self.after(2500,self._poll_pairing_status)

    def _disable_phone(self):
        updated=replace(self.settings);updated.remote_enabled=False;updated.save();self.settings=updated;self.on_save(updated);self._refresh_remote_status()

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
            self._save_pairing(show_qr=True)
        except Exception:self.status.configure(text=self.t('تعذر استيراد ملف إعداد الخادم.','Could not import server setup file.'))

    def _save_pairing(self,show_qr=False):
        if getattr(self,"_pairing_page_mode","")=="home":return self._save_home_pairing()
        from ..remote.settings import save_relay_enrollment,load_relay_enrollment,load_remote_token,generate_remote_token
        from ..remote.relay_protocol import origin
        try:
            if not self.security or not self.security.unlocked:raise ValueError(self.t('افتح قفل البرنامج أولاً.','Unlock the app first.'))
            updated=replace(self.settings)
            updated.remote_relay_url=origin(self._value('remote_relay_url',self.settings.remote_relay_url))
            enrollment=str(self._value('relay_enrollment_input','')).strip()
            if not enrollment and not load_relay_enrollment(self.security):raise ValueError(self.t('أدخل مفتاح تسجيل الخادم أولاً.','Enter the relay enrollment key first.'))
            for name in ('remote_desktop_enabled','remote_ai_enabled','remote_files_all_drives','remote_keep_awake'):
                if name in self.vars:setattr(updated,name,bool(self._value(name,getattr(updated,name))))
            if updated.remote_ai_enabled and not updated.remote_desktop_enabled:raise ValueError(self.t('فعّل الشاشة والملفات لاستخدام مساعد الكمبيوتر.','Enable screen and files to use computer AI.'))
            if enrollment:save_relay_enrollment(self.security,enrollment)
            if not load_remote_token(self.security):generate_remote_token(self.security)
            updated.remote_enabled=True;updated.remote_connection_mode='relay'
            updated.save();self.settings=updated;self.on_save(updated)
            if 'relay_enrollment_input' in self.vars:self.vars['relay_enrollment_input'].set('')
            self.status.configure(text=self.t('تم الحفظ؛ جارٍ الاتصال بالخادم.','Saved; connecting to relay.'));self._refresh_remote_status()
            if show_qr:self._show_pairing_qr()
        except (ValueError,OSError,SecurityError) as exc:self.status.configure(text=str(exc))

    def _show_pairing_qr(self):
        from ..remote.settings import pairing_payload,load_remote_token
        try:
            if not self.security or not self.security.unlocked:raise ValueError(self.t('افتح قفل البرنامج أولاً.','Unlock the app first.'))
            if getattr(self,'_pairing_page_mode','')=='home':
                if self.settings.remote_connection_mode!='home' or not self.settings.remote_enabled:raise ValueError(self.t('اضغط تشغيل الاستضافة على الكمبيوتر أولاً ليظهر QR.','Start hosting on this computer first to display QR.'))
                if self.remote_ready and not self.remote_ready():raise ValueError(self.t('تعذر تشغيل خادم الكمبيوتر. راجع المنفذ وحالة الاتصال قبل الاقتران.','Computer server did not start. Check its port and connection status before pairing.'))
                from ..remote.home import pairing_payload as home_payload
                payload=home_payload(self.security,load_remote_token(self.security),self.settings.remote_home_port,self.settings.remote_home_public_url,self.settings.remote_home_lan_url)
            else:
                if self.settings.remote_connection_mode!='relay' or not self.settings.remote_relay_url:raise ValueError(self.t('الخادم غير مجهّز بعد. استورد ملف إعداد الخادم في الخطوة ١؛ بعدها سيظهر الرمز هنا.','Relay is not configured yet. Import the server setup in step 1, then your QR will appear here.'))
                payload=pairing_payload(self.settings.remote_relay_url,load_remote_token(self.security))
            from PIL import ImageTk
            # Keep integer module sizes so scanners see sharp edges at any DPI.
            from .pairing_qr import pairing_qr_image
            image=pairing_qr_image(payload)
            panel=getattr(self,'_qr_panel',None)
            if panel is None or not panel.winfo_exists():
                dialog=tk.Toplevel(self);dialog.title(self.t('اقتران الهاتف','Pair phone'));panel=ttk.Frame(dialog,padding=18);panel.pack()
            for child in panel.winfo_children():child.destroy()
            photo=ImageTk.PhotoImage(image,master=panel)
            label=ttk.Label(panel,image=photo);label.image=photo;label.pack(anchor='w',pady=8)
            ttk.Label(panel,text=self.t('افتح Android واضغط مسح QR. هذا الرمز خاص بك.','Open Android and tap Scan QR. Keep this code private.'),wraplength=480).pack(anchor='w')
            self._canvas.yview_moveto(0)
            return True

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
        self._row_check(f,0,self.t("إتاحة كل الأقراص المحلية للهاتف", "Expose all local drives to the phone"),"remote_files_all_drives",self.settings.remote_files_all_drives)
        self._row_entry(f,1,self.t("المجلد", "Folder"),"remote_files_root",self.settings.remote_files_root)
        def choose():
            folder=filedialog.askdirectory(parent=self,mustexist=True)
            if folder:self.vars['remote_files_root'].set(folder)
        ttk.Button(f,text=self.t("اختيار المجلد أو القرص", "Choose folder or drive"),command=choose).grid(row=2,column=1,sticky='w')

    def _refresh_remote_status(self):
        label=getattr(self,"_remote_status_label",None)
        if label is not None:
            text=self.remote_status() if self.remote_status else self.t("احفظ الإعدادات لتطبيق الاتصال.", "Save settings to apply the connection.")
            if self.current=='pairing' and getattr(self,'_pairing_page_mode','')=='home':
                if self.settings.remote_connection_mode!='home' or not self.settings.remote_enabled:
                    text=self.t('الاستضافة المحلية متوقفة — اضغط تشغيل الاستضافة أدناه','Home hosting is stopped — start hosting below')
            elif self.current=='pairing' and not self.settings.remote_relay_url:
                text=self.t('١ / ٣  •  الخادم غير مجهّز — ابدأ باستيراد ملف الإعداد','1 / 3  •  Relay not configured — import server setup first')
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
            if self.current=="pairing":self._show_pairing_qr()
            else:self._show_pairing_token()
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
        if self.current == "pairing":return self._save_pairing(show_qr=True)
        if self.current == "desktop":
            try:
                updated=replace(self.settings)
                updated.remote_desktop_enabled=bool(self._value('remote_desktop_enabled',False))
                updated.remote_ai_enabled=bool(self._value('remote_ai_enabled',False)) and updated.remote_desktop_enabled
                updated.remote_files_all_drives=bool(self._value('remote_files_all_drives',False))
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
