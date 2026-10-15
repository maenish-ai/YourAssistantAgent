from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from ..config import Settings
from ..security.manager import SecurityManager, SecurityError
from . import theme
from .i18n import ui_text


class SetupWizard(tk.Toplevel):
    """First-run wizard. Optional service steps can be skipped."""

    def __init__(self, master, settings: Settings, security: SecurityManager, on_complete):
        super().__init__(master)
        self.settings = settings
        self.security = security
        self.on_complete = on_complete
        self.step = 0
        self.recovery_key = ""
        self.title("Your Assistant Agent Setup")
        self.geometry("720x560")
        self.minsize(660, 520)
        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.configure(bg=theme.BG)
        self.body = ttk.Frame(self, padding=28)
        self.body.pack(fill="both", expand=True)
        self.footer = ttk.Frame(self, padding=(28, 0, 28, 22))
        self.footer.pack(fill="x")
        self.back_btn = ttk.Button(self.footer, text="Back", command=self.back)
        self.back_btn.pack(side="left")
        self.next_btn = ttk.Button(self.footer, text="Next", style="Accent.TButton", command=self.next)
        self.next_btn.pack(side="right")
        self._render()

    def t(self, ar: str, en: str) -> str:
        return ui_text(ar, en, self.settings.interface_language)

    def _clear(self):
        for w in self.body.winfo_children():
            w.destroy()

    def _render(self):
        self._clear()
        self.back_btn.state(["disabled"] if self.step == 0 else ["!disabled"])
        if self.step == 0:
            self._language_page()
        elif self.step == 1:
            self._security_page()
        elif self.step == 2:
            self._services_page()
        else:
            self._finish_page()

    def _title(self, text: str, sub: str = ""):
        ttk.Label(self.body, text=text, style="Title.TLabel").pack(anchor="w", pady=(0, 8))
        if sub:
            ttk.Label(self.body, text=sub, style="Muted.TLabel", wraplength=620).pack(anchor="w", pady=(0, 20))

    def _language_page(self):
        self._title("Choose language / اختر اللغة", "The app will use one language at a time. You can change it later in Settings.")
        self.lang_var = tk.StringVar(value=self.settings.interface_language if self.settings.interface_language in {"ar", "en"} else "ar")
        box = ttk.LabelFrame(self.body, text="Language / اللغة", padding=18)
        box.pack(fill="x")
        ttk.Radiobutton(box, text="العربية", value="ar", variable=self.lang_var).pack(anchor="w", pady=8)
        ttk.Radiobutton(box, text="English", value="en", variable=self.lang_var).pack(anchor="w", pady=8)
        self.next_btn.config(text="Next / التالي")

    def _security_page(self):
        self._title(self.t("حماية البرنامج", "Protect the app"), self.t(
            "اختر متى يطلب البرنامج كلمة المرور. مفتاح الاسترداد سيظهر مرة واحدة عند إنشاء الحماية.",
            "Choose when the app asks for your password. A recovery key will be shown once when security is created.",
        ))
        self.mode_var = tk.StringVar(value=self.settings.password_mode)
        box = ttk.LabelFrame(self.body, text=self.t("طريقة القفل", "Lock mode"), padding=16)
        box.pack(fill="x", pady=(0, 14))
        for value, ar, en in [
            ("every_launch", "كل مرة يفتح البرنامج", "Every app launch"),
            ("windows_session", "مرة بعد تشغيل Windows", "Once per Windows session"),
            ("none", "بدون كلمة مرور", "No app password"),
        ]:
            ttk.Radiobutton(box, text=self.t(ar, en), value=value, variable=self.mode_var, command=self._toggle_password_fields).pack(anchor="w", pady=5)
        pw = ttk.Frame(self.body)
        pw.pack(fill="x")
        ttk.Label(pw, text=self.t("كلمة المرور", "Password")).grid(row=0, column=0, sticky="w", pady=6)
        ttk.Label(pw, text=self.t("تأكيد كلمة المرور", "Confirm password")).grid(row=1, column=0, sticky="w", pady=6)
        self.password = ttk.Entry(pw, show="•", width=36)
        self.password.grid(row=0, column=1, sticky="w", padx=12, pady=6)
        self.password2 = ttk.Entry(pw, show="•", width=36)
        self.password2.grid(row=1, column=1, sticky="w", padx=12, pady=6)
        self._toggle_password_fields()
        self.next_btn.config(text=self.t("التالي", "Next"))

    def _toggle_password_fields(self):
        state = "disabled" if self.mode_var.get() == "none" else "normal"
        try:
            self.password.configure(state=state)
            self.password2.configure(state=state)
        except Exception:
            pass

    def _services_page(self):
        self._title(self.t("الخدمات الاختيارية", "Optional services"), self.t(
            "تقدر تتخطاها الآن وتربطها لاحقًا من الإعدادات.",
            "You can skip these now and connect them later from Settings.",
        ))
        drive = ttk.LabelFrame(self.body, text="Google Drive", padding=16)
        drive.pack(fill="x", pady=(0, 12))
        ttk.Label(drive, text=self.t("OAuth Client ID", "OAuth Client ID")).grid(row=0, column=0, sticky="w")
        self.drive_id = ttk.Entry(drive, width=54)
        self.drive_id.grid(row=0, column=1, sticky="ew", padx=10)
        self.drive_id.insert(0, self.settings.google_drive_client_id)
        ttk.Label(drive, text=self.t("اختياري الآن. الربط الفعلي يتم من صفحة Backup.", "Optional now. Actual connection happens from Backup."), style="Muted.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        fb = ttk.LabelFrame(self.body, text="Facebook", padding=16)
        fb.pack(fill="x", pady=(0, 12))
        ttk.Label(fb, text=self.t("صفحة المصدر الافتراضية", "Default source page")).grid(row=0, column=0, sticky="w")
        self.source_page = ttk.Entry(fb, width=54)
        self.source_page.grid(row=0, column=1, sticky="ew", padx=10)
        self.source_page.insert(0, self.settings.default_source_page)
        ttk.Label(fb, text=self.t("تسجيل الدخول يتم لاحقًا من صفحة Facebook وبشكل يدوي عند الحاجة.", "Login happens later from the Facebook page and remains manual when needed."), style="Muted.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.next_btn.config(text=self.t("التالي", "Next"))

    def _finish_page(self):
        self._title(self.t("جاهز تقريبًا", "Almost ready"), self.t(
            "Hammer هو العقل المحلي الوحيد. Facebook وGoogle Drive اختياريان ويمكن ربطهما لاحقًا.",
            "Hammer is the only local AI brain. Facebook and Google Drive are optional and can be connected later.",
        ))
        if self.recovery_key:
            box = ttk.LabelFrame(self.body, text=self.t("مفتاح الاسترداد — احفظه الآن", "Recovery key — save it now"), padding=16)
            box.pack(fill="x", pady=(0, 16))
            recovery = tk.Text(box, height=3, wrap="word", font=("Consolas", 11), relief="flat")
            recovery.pack(fill="x")
            recovery.insert("1.0", self.recovery_key)
            recovery.configure(state="disabled")
            ttk.Label(box, text=self.t(
                "لا يتم حفظ المفتاح كنص داخل البرنامج. تحتاجه إذا نسيت كلمة المرور.",
                "The key is not stored as readable text in the app. Keep it somewhere safe in case you forget the password.",
            ), style="Muted.TLabel", wraplength=600).pack(anchor="w", pady=(8, 0))
        ttk.Label(self.body, text=self.t("بعد إنهاء الإعداد سيفتح Home ثم تقدر تبدأ المحادثة.", "After setup, Home opens and you can start chatting."), style="CardTitle.TLabel").pack(anchor="w", pady=10)
        self.next_btn.config(text=self.t("إنهاء", "Finish"))

    def next(self):
        if self.step == 0:
            self.settings.interface_language = self.lang_var.get()
            self.step = 1
            self._render()
            return
        if self.step == 1:
            mode = self.mode_var.get()
            pw = self.password.get() if mode != "none" else ""
            if mode != "none":
                if len(pw) < 4:
                    messagebox.showerror(self.t("خطأ", "Error"), self.t("كلمة المرور لازم تكون 4 أحرف على الأقل.", "Password must be at least 4 characters."), parent=self)
                    return
                if pw != self.password2.get():
                    messagebox.showerror(self.t("خطأ", "Error"), self.t("كلمتا المرور غير متطابقتين.", "Passwords do not match."), parent=self)
                    return
            try:
                if not self.security.configured:
                    self.recovery_key = self.security.setup(pw, mode)
                self.settings.password_mode = mode
            except SecurityError as exc:
                messagebox.showerror(self.t("خطأ", "Error"), str(exc), parent=self)
                return
            self.step = 2
            self._render()
            return
        if self.step == 2:
            self.settings.google_drive_client_id = self.drive_id.get().strip()
            self.settings.default_source_page = self.source_page.get().strip()
            self.step = 3
            self._render()
            return
        self.settings.first_run_complete = True
        self.settings.save()
        self.grab_release()
        self.destroy()
        self.on_complete()

    def back(self):
        if self.step > 0:
            self.step -= 1
            self._render()

    def _cancel(self):
        if messagebox.askyesno("Your Assistant Agent", "Exit setup?", parent=self):
            self.master.destroy()
