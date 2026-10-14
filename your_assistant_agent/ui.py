from __future__ import annotations

import csv
import math
import os
import sys
import time

from PySide6.QtCore import Qt, QEventLoop, QProcess, QTimer, QTime
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPushButton, QSpinBox, QTabWidget,
    QTableWidget, QTableWidgetItem, QTextEdit, QTimeEdit, QVBoxLayout, QWidget,
    QSystemTrayIcon, QMenu
)

from .branding import pixmap, window_icon
from .browser_discovery import discover_installed_browsers
from .db import Database
from .engine import AgentEngine
from .i18n import LANGUAGES, Translator
from .security import SecurityManager
from .smart_agent import SmartPlanner, SmartPlannerError
from .startup import is_enabled as startup_is_enabled, migrate_legacy_startup, set_enabled as startup_set_enabled
from .text_utils import is_valid_international_phone

APP_TITLE = "Your Assistant Agent"

EVENT_AR = {
    "engine_started": "بدء محرك الوكيل",
    "engine_stopped": "إيقاف محرك الوكيل",
    "group_added": "إضافة مجموعة فيسبوك",
    "campaign_added": "إضافة حملة فيسبوك",
    "campaign_queued": "إضافة حملة فيسبوك إلى الطابور",
    "campaign_no_groups": "لا توجد مجموعات مطابقة",
    "group_post_done": "تم نشر منشور المجموعة",
    "group_post_failed": "فشل نشر منشور المجموعة",
    "groups_discovery_queued": "تم إرسال طلب اكتشاف مجموعات فيسبوك",
    "groups_discovery_started": "بدء اكتشاف مجموعات فيسبوك",
    "groups_discovery_done": "اكتمل اكتشاف مجموعات فيسبوك",
    "groups_discovery_empty": "لم يتم العثور على مجموعات فيسبوك",
    "groups_discovery_failed": "فشل اكتشاف مجموعات فيسبوك",
    "groups_discovered": "تم حفظ مجموعات فيسبوك المكتشفة",
    "smart_rule_added": "إضافة قاعدة ذكية",
    "smart_rule_start": "بدء قاعدة ذكية",
    "smart_rule_queued": "إضافة قاعدة ذكية إلى الطابور",
    "smart_rule_no_groups": "لا توجد مجموعات مطابقة للقاعدة الذكية",
    "smart_group_share_done": "تمت المشاركة الذكية في المجموعة",
    "smart_group_share_failed": "فشلت المشاركة الذكية في المجموعة",
    "smart_rule_all_deduped": "تم تخطي التكرار في القاعدة الذكية",
    "telegram_remote_started": "بدء التحكم عبر تيليجرام",
    "telegram_remote_stopped": "إيقاف التحكم عبر تيليجرام",
    "telegram_remote_error": "خطأ في التحكم عبر تيليجرام",
    "telegram_unauthorized_user": "محاولة تيليجرام من مستخدم غير مصرح",
    "telegram_test": "اختبار اتصال تيليجرام",
    "facebook_browser_opened": "تم فتح متصفح فيسبوك",
    "facebook_manual_login_opened": "تم فتح تسجيل دخول فيسبوك اليدوي",
    "facebook_connection_checked": "تم التحقق من جلسة فيسبوك",
    "facebook_profile_in_use": "ملف متصفح فيسبوك ما زال مستخدمًا",
    "facebook_connection_check_failed": "فشل التحقق من اتصال فيسبوك",
    "facebook_browser_changed": "تم تغيير متصفح فيسبوك",
    "facebook_login_required": "يلزم تسجيل الدخول إلى فيسبوك",
    "facebook_checkpoint": "تحقق أمني من فيسبوك",
    "wa_contact_added": "إضافة جهة اتصال واتساب",
    "wa_campaign_added": "إضافة حملة واتساب",
    "wa_campaign_queued": "إضافة حملة واتساب إلى الطابور",
    "wa_campaign_no_contacts": "لا توجد جهات اتصال مؤهلة",
    "wa_message_done": "تم إرسال رسالة واتساب",
    "wa_message_failed": "فشل إرسال رسالة واتساب",
    "wa_not_configured": "واتساب غير مهيأ",
    "emergency_stop": "إيقاف طارئ",
    "startup_changed": "تغيير التشغيل مع ويندوز",
    "secret_updated": "تحديث سر محمي",
    "pin_set": "إنشاء رمز PIN",
    "pin_failed": "محاولة PIN غير صحيحة",
}


class LanguageDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Language / اللغة")
        self.setWindowIcon(window_icon())
        self.setModal(True)
        self.setFixedWidth(430)
        root = QVBoxLayout(self)
        root.setSpacing(16)

        logo = QLabel()
        pm = pixmap("brand_mark.png")
        if not pm.isNull():
            logo.setPixmap(pm.scaled(180, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setAlignment(Qt.AlignCenter)
        root.addWidget(logo)

        title = QLabel("Choose language  |  اختر اللغة")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:20px;font-weight:800;color:#1f2455;")
        root.addWidget(title)

        self.combo = QComboBox()
        self.combo.addItem("العربية", "ar")
        self.combo.addItem("English", "en")
        self.combo.setCurrentIndex(0)
        root.addWidget(self.combo)

        btn = QPushButton("متابعة  |  Continue")
        btn.setMinimumHeight(40)
        btn.clicked.connect(self.accept)
        root.addWidget(btn)

    @property
    def language(self):
        return self.combo.currentData() or "ar"


class SplashWidget(QWidget):
    def __init__(self, tr: Translator):
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.tr = tr
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setFixedSize(610, 570)
        self.setStyleSheet("background:white;border:1px solid #ececff;")
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 30, 36, 28)
        root.setSpacing(10)

        mark = QLabel()
        pm = pixmap("brand_mark.png")
        if not pm.isNull():
            mark.setPixmap(pm.scaled(360, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        mark.setAlignment(Qt.AlignCenter)
        root.addWidget(mark)

        title = QLabel(APP_TITLE)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:35px;font-weight:800;color:#20285c;")
        root.addWidget(title)

        desc = QLabel(tr.t("splash_desc"))
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size:14px;color:#60658a;")
        root.addWidget(desc)

        features = QLabel(tr.t("splash_features"))
        features.setAlignment(Qt.AlignCenter)
        features.setWordWrap(True)
        features.setStyleSheet("font-size:12px;color:#7668ce;")
        root.addWidget(features)

        init = QLabel(tr.t("initializing"))
        init.setAlignment(Qt.AlignCenter)
        init.setStyleSheet("font-size:12px;color:#8a8da8;margin-top:14px;")
        root.addWidget(init)


class BrandBanner(QWidget):
    def __init__(self, tr: Translator, subtitle: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        logo = QLabel()
        pm = pixmap("app_icon.png")
        if not pm.isNull():
            logo.setPixmap(pm.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        lay.addWidget(logo)
        txt = QVBoxLayout()
        head = QLabel(APP_TITLE)
        head.setStyleSheet("font-size:23px;font-weight:800;color:#20285c;")
        sub = QLabel(subtitle)
        sub.setWordWrap(True)
        sub.setStyleSheet("font-size:12px;color:#6b7280;")
        txt.addWidget(head)
        txt.addWidget(sub)
        lay.addLayout(txt, 1)


class PinDialog(QDialog):
    def __init__(self, security: SecurityManager, tr: Translator, create=False, parent=None):
        super().__init__(parent)
        self.security = security
        self.tr = tr
        self.create = create
        self.setWindowTitle(f"{APP_TITLE} - {tr.t('security')}")
        self.setWindowIcon(window_icon())
        self.setModal(True)
        self.setMinimumWidth(470)
        self.setLayoutDirection(Qt.RightToLeft if tr.rtl else Qt.LeftToRight)

        root = QVBoxLayout(self)
        root.addWidget(BrandBanner(tr, tr.t("security")))
        form = QFormLayout()
        self.pin = QLineEdit()
        self.pin.setEchoMode(QLineEdit.Password)
        form.addRow((tr.t("create_pin") if create else tr.t("pin")) + ":", self.pin)
        self.confirm = None
        if create:
            self.confirm = QLineEdit()
            self.confirm.setEchoMode(QLineEdit.Password)
            form.addRow(tr.t("confirm_pin") + ":", self.confirm)
        root.addLayout(form)
        note = QLabel(tr.t("pin_note"))
        note.setWordWrap(True)
        note.setStyleSheet("color:#6b7280;")
        root.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(tr.t("continue"))
        buttons.button(QDialogButtonBox.Cancel).setText(tr.t("cancel"))
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _accept(self):
        value = self.pin.text()
        if self.create:
            if len(value) < 4:
                QMessageBox.warning(self, self.tr.t("pin"), self.tr.t("pin_min"))
                return
            if value != self.confirm.text():
                QMessageBox.warning(self, self.tr.t("pin"), self.tr.t("pin_mismatch"))
                return
            self.security.set_pin(value)
            self.accept()
            return
        if not self.security.verify_pin(value):
            QMessageBox.warning(self, self.tr.t("pin"), self.tr.t("pin_wrong"))
            return
        self.accept()


class BrowserChoiceDialog(QDialog):
    def __init__(self, tr: Translator, current_choice: str = "auto", parent=None):
        super().__init__(parent)
        self.tr = tr
        self.current_choice = current_choice or "auto"
        self.options: list[dict] = []
        self.setWindowTitle(tr.t("facebook_browser"))
        self.setWindowIcon(window_icon())
        self.setModal(True)
        self.setMinimumWidth(650)
        self.setLayoutDirection(Qt.RightToLeft if tr.rtl else Qt.LeftToRight)

        root = QVBoxLayout(self)
        title = QLabel(tr.t("choose_browser"))
        title.setWordWrap(True)
        title.setStyleSheet("font-size:17px;font-weight:800;color:#20285c;")
        root.addWidget(title)

        note = QLabel(tr.t("browser_first_time"))
        note.setWordWrap(True)
        note.setStyleSheet("color:#6b7280;")
        root.addWidget(note)

        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self._update_details)
        root.addWidget(self.combo)

        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.details.setStyleSheet("padding:10px;background:#f7f7fb;border:1px solid #e5e7eb;border-radius:6px;color:#4b5563;")
        root.addWidget(self.details)

        row = QHBoxLayout()
        refresh = QPushButton(tr.t("browser_refresh"))
        refresh.clicked.connect(self.reload)
        row.addWidget(refresh)
        row.addStretch(1)
        cancel = QPushButton(tr.t("cancel")); cancel.clicked.connect(self.reject)
        use = QPushButton(tr.t("browser_apply")); use.clicked.connect(self._accept_choice)
        row.addWidget(cancel); row.addWidget(use)
        root.addLayout(row)

        self.reload()

    def _support_text(self, support: str) -> str:
        return self.tr.t({
            "full": "browser_support_full",
            "experimental": "browser_support_experimental",
            "unsupported": "browser_support_unsupported",
        }.get(support, "browser_support_experimental"))

    def reload(self):
        previous = self.current_choice
        if self.combo.currentIndex() >= 0 and self.options:
            previous = self.options[self.combo.currentIndex()].get("choice", previous)

        self.combo.blockSignals(True)
        self.combo.clear()
        self.options = []

        self._add_option(self.tr.t("browser_auto"), "auto", self.tr.t("browser_auto"), "full", "")
        for browser in discover_installed_browsers():
            support = browser.support
            visible = f"{browser.name} — {self._support_text(support)}"
            self._add_option(visible, browser.key, browser.name, support, str(browser.executable))
        self._add_option(self.tr.t("browser_bundled"), "bundled", self.tr.t("browser_bundled"), "full", "")

        idx = next((i for i, opt in enumerate(self.options) if opt["choice"].casefold() == str(previous).casefold()), 0)
        self.combo.setCurrentIndex(idx)
        self.combo.blockSignals(False)
        self._update_details()

    def _add_option(self, visible: str, choice: str, label: str, support: str, path: str):
        self.options.append({"choice": choice, "label": label, "support": support, "path": path})
        self.combo.addItem(visible)

    def _update_details(self):
        if self.combo.currentIndex() < 0 or not self.options:
            self.details.clear(); return
        opt = self.options[self.combo.currentIndex()]
        lines = [f"{self.tr.t('browser_current')}: {opt['label']}", self._support_text(opt["support"])]
        if opt["path"]:
            lines.append(f"{self.tr.t('browser_path')}: {opt['path']}")
        self.details.setText("\n".join(lines))

    def _accept_choice(self):
        if self.combo.currentIndex() < 0:
            QMessageBox.warning(self, self.tr.t("facebook_browser"), self.tr.t("browser_select_first"))
            return
        opt = self.options[self.combo.currentIndex()]
        if opt["support"] == "unsupported":
            QMessageBox.warning(self, self.tr.t("facebook_browser"), self.tr.t("browser_unsupported_warning"))
            return
        if opt["support"] == "experimental":
            answer = QMessageBox.question(self, self.tr.t("facebook_browser"), self.tr.t("browser_experimental_warning"))
            if answer != QMessageBox.Yes:
                return
        self.accept()

    @property
    def selection(self) -> dict:
        if self.combo.currentIndex() < 0 or not self.options:
            return {"choice": "auto", "label": self.tr.t("browser_auto"), "support": "full"}
        return dict(self.options[self.combo.currentIndex()])


class MainWindow(QMainWindow):
    def __init__(self, db: Database, engine: AgentEngine, security: SecurityManager, tr: Translator):
        super().__init__()
        self.db = db
        self.engine = engine
        self.security = security
        self.tr = tr
        self._really_quit = False
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(window_icon())
        self.resize(1280, 820)
        self.setLayoutDirection(Qt.RightToLeft if tr.rtl else Qt.LeftToRight)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.dashboard = QWidget()
        self.groups_tab = QWidget()
        self.campaigns_tab = QWidget()
        self.smart_tab = QWidget()
        self.whatsapp_tab = QWidget()
        self.logs_tab = QWidget()
        self.settings_tab = QWidget()
        self.tabs.addTab(self.dashboard, tr.t("dashboard"))
        self.tabs.addTab(self.groups_tab, tr.t("facebook_groups"))
        self.tabs.addTab(self.campaigns_tab, tr.t("facebook_campaigns"))
        self.tabs.addTab(self.smart_tab, tr.t("smart_agent"))
        self.tabs.addTab(self.whatsapp_tab, tr.t("whatsapp"))
        self.tabs.addTab(self.logs_tab, tr.t("audit_log"))
        self.tabs.addTab(self.settings_tab, tr.t("settings"))

        self._build_dashboard()
        self._build_groups()
        self._build_campaigns()
        self._build_smart()
        self._build_whatsapp()
        self._build_logs()
        self._build_settings()
        self._build_tray()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_all)
        self.timer.start(2500)
        self.refresh_all()

    def _build_dashboard(self):
        lay = QVBoxLayout(self.dashboard)
        lay.addWidget(BrandBanner(self.tr, self.tr.t("dashboard_subtitle")))
        buttons = QHBoxLayout()
        self.login_btn = QPushButton(self.tr.t("open_facebook"))
        self.login_btn.clicked.connect(self.open_facebook_browser)
        self.check_fb_btn = QPushButton(self.tr.t("check_facebook_connection"))
        self.check_fb_btn.clicked.connect(self.check_facebook_connection)
        self.pause_btn = QPushButton()
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.kill_btn = QPushButton(self.tr.t("emergency_stop"))
        self.kill_btn.setStyleSheet("font-weight:800;padding:8px;")
        self.kill_btn.clicked.connect(self.emergency_stop)
        self.startup_check = QCheckBox(self.tr.t("start_windows"))
        try:
            self.startup_check.setChecked(startup_is_enabled())
        except Exception:
            self.startup_check.setChecked(False)
        self.startup_check.toggled.connect(self.toggle_startup)
        buttons.addWidget(self.login_btn)
        buttons.addWidget(self.check_fb_btn)
        buttons.addWidget(self.pause_btn)
        buttons.addWidget(self.kill_btn)
        buttons.addWidget(self.startup_check)
        lay.addLayout(buttons)

        box = QGroupBox(self.tr.t("status"))
        grid = QGridLayout(box)
        self.status_label = QLabel()
        self.fb_status_label = QLabel()
        self.queue_label = QLabel()
        self.next_label = QLabel()
        self.smart_next_label = QLabel()
        self.wa_next_label = QLabel()
        grid.addWidget(QLabel(self.tr.t("agent") + ":"), 0, 0)
        grid.addWidget(self.status_label, 0, 1)
        grid.addWidget(QLabel(self.tr.t("facebook_connection") + ":"), 1, 0)
        grid.addWidget(self.fb_status_label, 1, 1)
        grid.addWidget(QLabel(self.tr.t("queue") + ":"), 2, 0)
        grid.addWidget(self.queue_label, 2, 1)
        grid.addWidget(QLabel(self.tr.t("next_campaign") + ":"), 3, 0)
        grid.addWidget(self.next_label, 3, 1)
        grid.addWidget(QLabel(self.tr.t("next_smart_rule") + ":"), 4, 0)
        grid.addWidget(self.smart_next_label, 4, 1)
        grid.addWidget(QLabel(self.tr.t("next_wa_campaign") + ":"), 5, 0)
        grid.addWidget(self.wa_next_label, 5, 1)
        lay.addWidget(box)
        note = QLabel(self.tr.t("facebook_note"))
        note.setWordWrap(True)
        lay.addWidget(note)
        lay.addStretch(1)

    def _build_groups(self):
        lay = QVBoxLayout(self.groups_tab)
        helper = QLabel(self.tr.t("group_help")); helper.setWordWrap(True); helper.setStyleSheet("color:#6b7280;")
        lay.addWidget(helper)
        form = QHBoxLayout()
        self.g_name = QLineEdit(); self.g_name.setPlaceholderText(self.tr.t("group_name"))
        self.g_url = QLineEdit(); self.g_url.setPlaceholderText("https://www.facebook.com/groups/...")
        self.g_tags = QLineEdit(); self.g_tags.setPlaceholderText(self.tr.t("tags"))
        add = QPushButton(self.tr.t("add_group")); add.clicked.connect(self.add_group)
        form.addWidget(self.g_name, 2); form.addWidget(self.g_url, 4); form.addWidget(self.g_tags, 2); form.addWidget(add)
        lay.addLayout(form)
        self.groups_table = QTableWidget(0, 5)
        self.groups_table.setHorizontalHeaderLabels([self.tr.t("id"), self.tr.t("group_name"), self.tr.t("url"), self.tr.t("tags"), self.tr.t("enabled")])
        self.groups_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lay.addWidget(self.groups_table)
        self.group_discovery_status = QLabel("")
        self.group_discovery_status.setWordWrap(True)
        self.group_discovery_status.setStyleSheet("color:#4b5563;")
        lay.addWidget(self.group_discovery_status)
        buttons = QHBoxLayout()
        self.discover_btn = QPushButton(self.tr.t("discover_groups")); self.discover_btn.clicked.connect(self.discover_groups)
        delete = QPushButton(self.tr.t("delete_group")); delete.clicked.connect(self.delete_group)
        buttons.addWidget(self.discover_btn); buttons.addWidget(delete); buttons.addStretch(1); lay.addLayout(buttons)

    def _build_campaigns(self):
        lay = QVBoxLayout(self.campaigns_tab)
        box = QGroupBox(self.tr.t("new_campaign"))
        form = QFormLayout(box)
        self.c_name = QLineEdit()
        self.c_page = QLineEdit(); self.c_page.setPlaceholderText("https://www.facebook.com/...")
        self.c_offset = QSpinBox(); self.c_offset.setRange(0, 20)
        self.c_keyword = QLineEdit()
        self.c_max = QSpinBox(); self.c_max.setRange(1, 100); self.c_max.setValue(10)
        self.c_interval = QSpinBox(); self.c_interval.setRange(30, 3600); self.c_interval.setValue(60); self.c_interval.setSuffix(self.tr.t("seconds"))
        self.c_days = QSpinBox(); self.c_days.setRange(1, 365); self.c_days.setValue(3); self.c_days.setSuffix(self.tr.t("days"))
        self.c_time = QTimeEdit(); self.c_time.setDisplayFormat("HH:mm"); self.c_time.setTime(QTime(20, 0))
        self.c_prefix = QLineEdit()
        for label, widget in [
            ("campaign_name", self.c_name), ("source_page", self.c_page), ("post_offset", self.c_offset),
            ("target_keyword", self.c_keyword), ("maximum_groups", self.c_max), ("delay_groups", self.c_interval),
            ("run_every", self.c_days), ("at", self.c_time), ("optional_prefix", self.c_prefix)
        ]:
            form.addRow(self.tr.t(label), widget)
        add = QPushButton(self.tr.t("create_campaign")); add.clicked.connect(self.add_campaign); form.addRow(add)
        lay.addWidget(box)

        self.campaign_table = QTableWidget(0, 10)
        self.campaign_table.setHorizontalHeaderLabels([
            self.tr.t("id"), self.tr.t("campaign_name"), self.tr.t("page"), self.tr.t("offset"),
            self.tr.t("keyword"), self.tr.t("max"), self.tr.t("delay"), self.tr.t("every_days"), self.tr.t("at"), self.tr.t("next_run")
        ])
        self.campaign_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.campaign_table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.campaign_table)
        row = QHBoxLayout()
        run = QPushButton(self.tr.t("run_now")); run.clicked.connect(self.run_campaign_now)
        toggle = QPushButton(self.tr.t("toggle_selected")); toggle.clicked.connect(self.toggle_campaign)
        delete = QPushButton(self.tr.t("delete_selected")); delete.clicked.connect(self.delete_campaign)
        row.addWidget(run); row.addWidget(toggle); row.addWidget(delete); lay.addLayout(row)

    def _build_smart(self):
        root = QVBoxLayout(self.smart_tab)
        note = QLabel(self.tr.t("smart_help")); note.setWordWrap(True); note.setStyleSheet("color:#5d6386;")
        root.addWidget(note)

        planner_box = QGroupBox(self.tr.t("smart_instruction"))
        form = QFormLayout(planner_box)
        self.smart_source = QLineEdit(str(self.db.get_setting("smart_default_source_page", "") or ""))
        self.smart_source.setPlaceholderText("https://www.facebook.com/...")
        self.smart_command = QTextEdit(); self.smart_command.setMaximumHeight(105); self.smart_command.setPlaceholderText(self.tr.t("smart_example"))
        self.smart_preview = QTextEdit(); self.smart_preview.setReadOnly(True); self.smart_preview.setMaximumHeight(150)
        form.addRow(self.tr.t("source_page"), self.smart_source)
        form.addRow(self.tr.t("smart_command"), self.smart_command)
        form.addRow(self.tr.t("smart_preview"), self.smart_preview)
        btns = QHBoxLayout()
        preview = QPushButton(self.tr.t("preview_plan")); preview.clicked.connect(self.preview_smart_rule)
        approve = QPushButton(self.tr.t("approve_rule")); approve.clicked.connect(self.approve_smart_rule)
        btns.addWidget(preview); btns.addWidget(approve); form.addRow(btns)
        root.addWidget(planner_box)
        self._pending_smart_plan = None

        self.smart_rules_table = QTableWidget(0, 8)
        self.smart_rules_table.setHorizontalHeaderLabels([
            self.tr.t("id"), self.tr.t("rule_name"), self.tr.t("keyword"), self.tr.t("post_selector"),
            self.tr.t("at"), self.tr.t("next_run"), self.tr.t("enabled"), self.tr.t("details")
        ])
        self.smart_rules_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.smart_rules_table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.smart_rules_table)
        actions = QHBoxLayout()
        run = QPushButton(self.tr.t("run_now")); run.clicked.connect(self.run_smart_rule_now)
        toggle = QPushButton(self.tr.t("toggle_selected")); toggle.clicked.connect(self.toggle_smart_rule)
        delete = QPushButton(self.tr.t("delete_selected")); delete.clicked.connect(self.delete_smart_rule)
        actions.addWidget(run); actions.addWidget(toggle); actions.addWidget(delete); actions.addStretch(1); root.addLayout(actions)

        tg = QGroupBox(self.tr.t("telegram_remote"))
        tg_form = QFormLayout(tg)
        self.telegram_enabled = QCheckBox(self.tr.t("telegram_enable")); self.telegram_enabled.setChecked(bool(self.db.get_setting("telegram_enabled", False)))
        self.telegram_user_id = QLineEdit(str(self.db.get_setting("telegram_authorized_user_id", "") or "")); self.telegram_user_id.setPlaceholderText("123456789")
        self.telegram_token = QLineEdit(); self.telegram_token.setEchoMode(QLineEdit.Password); self.telegram_token.setPlaceholderText(self.tr.t("telegram_token_placeholder"))
        self.telegram_status = QLabel(); self.telegram_status.setWordWrap(True)
        tg_form.addRow(self.telegram_enabled)
        tg_form.addRow(self.tr.t("telegram_user_id"), self.telegram_user_id)
        tg_form.addRow(self.tr.t("telegram_token"), self.telegram_token)
        tgb = QHBoxLayout()
        save = QPushButton(self.tr.t("save_telegram")); save.clicked.connect(self.save_telegram_settings)
        test = QPushButton(self.tr.t("test_telegram")); test.clicked.connect(self.test_telegram)
        tgb.addWidget(save); tgb.addWidget(test); tg_form.addRow(tgb); tg_form.addRow(self.telegram_status)
        root.addWidget(tg)

    def _build_whatsapp(self):
        root = QVBoxLayout(self.whatsapp_tab)
        info = QLabel(self.tr.t("wa_info")); info.setWordWrap(True); info.setStyleSheet("color:#5d6386;")
        root.addWidget(info)
        self.wa_tabs = QTabWidget(); root.addWidget(self.wa_tabs)
        contacts = QWidget(); campaigns = QWidget(); settings = QWidget()
        self.wa_tabs.addTab(contacts, self.tr.t("whatsapp_contacts"))
        self.wa_tabs.addTab(campaigns, self.tr.t("whatsapp_campaigns"))
        self.wa_tabs.addTab(settings, self.tr.t("whatsapp_settings"))
        self._build_wa_contacts(contacts)
        self._build_wa_campaigns(campaigns)
        self._build_wa_settings(settings)

    def _build_wa_contacts(self, widget):
        lay = QVBoxLayout(widget)
        note = QLabel(self.tr.t("wa_contact_help")); note.setWordWrap(True); note.setStyleSheet("color:#6b7280;"); lay.addWidget(note)
        form = QHBoxLayout()
        self.wa_name = QLineEdit(); self.wa_name.setPlaceholderText(self.tr.t("contact_name"))
        self.wa_phone = QLineEdit(); self.wa_phone.setPlaceholderText(self.tr.t("phone"))
        self.wa_tags = QLineEdit(); self.wa_tags.setPlaceholderText(self.tr.t("tags"))
        self.wa_optin = QCheckBox(self.tr.t("opt_in")); self.wa_optin.setChecked(True)
        add = QPushButton(self.tr.t("add_contact")); add.clicked.connect(self.add_wa_contact)
        form.addWidget(self.wa_name, 2); form.addWidget(self.wa_phone, 2); form.addWidget(self.wa_tags, 2); form.addWidget(self.wa_optin); form.addWidget(add)
        lay.addLayout(form)
        self.wa_contacts_table = QTableWidget(0, 6)
        self.wa_contacts_table.setHorizontalHeaderLabels([self.tr.t("id"), self.tr.t("contact_name"), self.tr.t("phone"), self.tr.t("tags"), self.tr.t("opt_in"), self.tr.t("enabled")])
        self.wa_contacts_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lay.addWidget(self.wa_contacts_table)
        buttons = QHBoxLayout()
        imp = QPushButton(self.tr.t("import_csv")); imp.clicked.connect(self.import_wa_csv)
        dele = QPushButton(self.tr.t("delete_contact")); dele.clicked.connect(self.delete_wa_contact)
        buttons.addWidget(imp); buttons.addWidget(dele); buttons.addStretch(1); lay.addLayout(buttons)

    def _build_wa_campaigns(self, widget):
        lay = QVBoxLayout(widget)
        box = QGroupBox(self.tr.t("whatsapp_campaigns"))
        form = QFormLayout(box)
        self.wac_name = QLineEdit()
        self.wac_mode = QComboBox(); self.wac_mode.addItem(self.tr.t("text_message"), "text"); self.wac_mode.addItem(self.tr.t("template_message"), "template")
        self.wac_message = QTextEdit(); self.wac_message.setMaximumHeight(90)
        self.wac_template = QLineEdit()
        self.wac_template_lang = QLineEdit("ar" if self.tr.rtl else "en_US")
        self.wac_keyword = QLineEdit()
        self.wac_batch = QSpinBox(); self.wac_batch.setRange(1, 256); self.wac_batch.setValue(100)
        self.wac_interval = QSpinBox(); self.wac_interval.setRange(30, 3600); self.wac_interval.setValue(60); self.wac_interval.setSuffix(self.tr.t("seconds"))
        self.wac_days = QSpinBox(); self.wac_days.setRange(1, 365); self.wac_days.setValue(1); self.wac_days.setSuffix(self.tr.t("days"))
        self.wac_time = QTimeEdit(); self.wac_time.setDisplayFormat("HH:mm"); self.wac_time.setTime(QTime(19, 0))
        for key, widget2 in [
            ("wa_campaign_name", self.wac_name), ("message_mode", self.wac_mode), ("message_text", self.wac_message),
            ("template_name", self.wac_template), ("template_language", self.wac_template_lang),
            ("target_contact_keyword", self.wac_keyword), ("batch_size", self.wac_batch), ("delay_contacts", self.wac_interval),
            ("run_every", self.wac_days), ("at", self.wac_time)
        ]:
            form.addRow(self.tr.t(key), widget2)
        row = QHBoxLayout()
        preview = QPushButton(self.tr.t("preview_batches")); preview.clicked.connect(self.preview_wa_batches)
        add = QPushButton(self.tr.t("create_wa_campaign")); add.clicked.connect(self.add_wa_campaign)
        row.addWidget(preview); row.addWidget(add); form.addRow(row)
        lay.addWidget(box)

        self.wa_campaign_table = QTableWidget(0, 9)
        self.wa_campaign_table.setHorizontalHeaderLabels([
            self.tr.t("id"), self.tr.t("wa_campaign_name"), self.tr.t("mode"), self.tr.t("keyword"), self.tr.t("batch"),
            self.tr.t("delay"), self.tr.t("every_days"), self.tr.t("at"), self.tr.t("next_run")
        ])
        self.wa_campaign_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.wa_campaign_table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.wa_campaign_table)
        buttons = QHBoxLayout()
        run = QPushButton(self.tr.t("run_now")); run.clicked.connect(self.run_wa_campaign_now)
        toggle = QPushButton(self.tr.t("toggle_selected")); toggle.clicked.connect(self.toggle_wa_campaign)
        delete = QPushButton(self.tr.t("delete_selected")); delete.clicked.connect(self.delete_wa_campaign)
        buttons.addWidget(run); buttons.addWidget(toggle); buttons.addWidget(delete); lay.addLayout(buttons)

    def _build_wa_settings(self, widget):
        lay = QVBoxLayout(widget)
        form = QFormLayout()
        self.wa_phone_id = QLineEdit(str(self.db.get_setting("wa_phone_number_id", "") or ""))
        self.wa_api_version = QLineEdit(str(self.db.get_setting("wa_api_version", "v24.0") or "v24.0"))
        self.wa_token = QLineEdit(); self.wa_token.setEchoMode(QLineEdit.Password); self.wa_token.setPlaceholderText(self.tr.t("wa_token_placeholder"))
        form.addRow(self.tr.t("wa_phone_id"), self.wa_phone_id)
        form.addRow(self.tr.t("wa_api_version"), self.wa_api_version)
        form.addRow(self.tr.t("wa_token"), self.wa_token)
        save = QPushButton(self.tr.t("save_wa_settings")); save.clicked.connect(self.save_wa_settings); form.addRow(save)
        lay.addLayout(form); lay.addStretch(1)

    def _build_logs(self):
        lay = QVBoxLayout(self.logs_tab)
        note = QLabel(self.tr.t("log_note")); note.setStyleSheet("color:#6b7280;"); lay.addWidget(note)
        self.logs_table = QTableWidget(0, 4)
        self.logs_table.setHorizontalHeaderLabels([self.tr.t("time"), self.tr.t("level"), self.tr.t("event"), self.tr.t("details")])
        self.logs_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lay.addWidget(self.logs_table)

    def _build_settings(self):
        lay = QVBoxLayout(self.settings_tab)

        browser_box = QGroupBox(self.tr.t("facebook_browser"))
        browser_layout = QVBoxLayout(browser_box)
        self.browser_current_label = QLabel()
        self.browser_current_label.setWordWrap(True)
        browser_layout.addWidget(self.browser_current_label)
        choose_browser = QPushButton(self.tr.t("browser_apply"))
        choose_browser.clicked.connect(lambda: self.choose_facebook_browser(open_after=False))
        browser_layout.addWidget(choose_browser)
        lay.addWidget(browser_box)
        self._refresh_browser_current_label()

        lang_box = QGroupBox(self.tr.t("language"))
        form = QFormLayout(lang_box)
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("العربية", "ar")
        self.lang_combo.addItem("English", "en")
        idx = self.lang_combo.findData(self.tr.language)
        if idx >= 0: self.lang_combo.setCurrentIndex(idx)
        apply = QPushButton(self.tr.t("apply_language")); apply.clicked.connect(self.apply_language)
        form.addRow(self.tr.t("language"), self.lang_combo); form.addRow(apply)
        lay.addWidget(lang_box)
        sec = QGroupBox(self.tr.t("about_security")); s = QVBoxLayout(sec); text = QLabel(self.tr.t("security_text")); text.setWordWrap(True); s.addWidget(text); lay.addWidget(sec)
        lay.addStretch(1)

    def _refresh_browser_current_label(self):
        if not hasattr(self, "browser_current_label"):
            return
        choice = str(self.db.get_setting("facebook_browser_choice", "auto") or "auto")
        label = str(self.db.get_setting("facebook_browser_label", "") or "")
        if not label:
            label = self.tr.t("browser_auto") if choice == "auto" else self.tr.t("browser_bundled") if choice == "bundled" else choice
        self.browser_current_label.setText(f"{self.tr.t('browser_current')}: {label}")

    def choose_facebook_browser(self, open_after: bool = False) -> bool:
        current = str(self.db.get_setting("facebook_browser_choice", "auto") or "auto")
        dlg = BrowserChoiceDialog(self.tr, current, self)
        if dlg.exec() != QDialog.Accepted:
            return False
        selected = dlg.selection
        payload = {"choice": selected["choice"], "label": selected["label"]}
        # Save immediately so the UI reflects the choice; the engine receives
        # the same values and safely restarts only its dedicated browser context.
        self.db.set_setting("facebook_browser_choice", payload["choice"])
        self.db.set_setting("facebook_browser_label", payload["label"])
        self.db.set_setting("facebook_browser_user_selected", True)
        self.db.set_setting("facebook_connection_status", "not_checked")
        self.engine.command("set_facebook_browser", payload)
        self._refresh_browser_current_label()
        if open_after:
            self._start_manual_facebook_login()
        else:
            QMessageBox.information(self, self.tr.t("facebook_browser"), self.tr.t("browser_saved"))
        return True

    def _start_manual_facebook_login(self):
        self.db.set_setting("facebook_connection_status", "manual_login")
        self.db.set_setting("facebook_manual_login_started_at", time.time())
        self.engine.command("open_login")
        QMessageBox.information(
            self,
            self.tr.t("manual_login_title"),
            self.tr.t("manual_login_instructions"),
        )

    def open_facebook_browser(self):
        selected_before = bool(self.db.get_setting("facebook_browser_user_selected", False))
        if not selected_before:
            self.choose_facebook_browser(open_after=True)
            return
        self._start_manual_facebook_login()

    def check_facebook_connection(self):
        self.db.set_setting("facebook_connection_status", "checking")
        self.engine.command("check_facebook_connection")

    def _build_tray(self):
        self.tray = QSystemTrayIcon(self); self.tray.setToolTip(APP_TITLE); self.tray.setIcon(window_icon())
        menu = QMenu(self)
        show = menu.addAction(APP_TITLE); show.triggered.connect(self.show_normal)
        stop = menu.addAction(self.tr.t("emergency_stop")); stop.triggered.connect(self.emergency_stop)
        menu.addSeparator(); exit_action = menu.addAction("Exit" if not self.tr.rtl else "خروج"); exit_action.triggered.connect(self.exit_app)
        self.tray.setContextMenu(menu); self.tray.activated.connect(lambda reason: self.show_normal() if reason == QSystemTrayIcon.DoubleClick else None); self.tray.show()

    def show_normal(self): self.show(); self.raise_(); self.activateWindow()
    def exit_app(self): self._really_quit = True; self.close()

    def toggle_startup(self, checked):
        try:
            startup_set_enabled(bool(checked)); self.db.audit("INFO", "startup_changed", str(bool(checked)))
        except Exception as exc:
            QMessageBox.warning(self, self.tr.t("settings"), str(exc))

    def toggle_pause(self):
        self.db.set_setting("paused", not bool(self.db.get_setting("paused", False))); self.refresh_all()

    def emergency_stop(self):
        if QMessageBox.question(self, self.tr.t("emergency_stop"), self.tr.t("emergency_question")) == QMessageBox.Yes:
            self.db.set_setting("paused", True); self.db.clear_pending(); self.db.audit("SECURITY", "emergency_stop"); self.refresh_all()

    def discover_groups(self):
        # Record the click immediately in the UI thread. This makes it obvious in
        # Audit Log whether the command was queued even before the worker starts.
        self.db.set_setting("facebook_group_discovery_result", {
            "status": "queued", "count": 0, "ts": time.time(), "error": ""
        })
        self.db.audit("INFO", "groups_discovery_queued")
        if hasattr(self, "group_discovery_status"):
            self.group_discovery_status.setText(self.tr.t("discover_groups_queued"))
        if hasattr(self, "discover_btn"):
            self.discover_btn.setEnabled(False)
        self.engine.command("discover_groups")

    def preview_smart_rule(self):
        source = self.smart_source.text().strip()
        self.db.set_setting("smart_default_source_page", source)
        planner = SmartPlanner(self.tr.language)
        try:
            plans = planner.parse_many(
                self.smart_command.toPlainText(),
                default_source_page=source,
                default_interval=int(self.db.get_setting("smart_default_interval_seconds", 60) or 60),
                default_max_groups=int(self.db.get_setting("smart_default_max_groups", 100) or 100),
                default_no_repeat_days=int(self.db.get_setting("smart_no_repeat_days", 14) or 14),
            )
        except SmartPlannerError as exc:
            QMessageBox.warning(self, self.tr.t("smart_agent"), str(exc)); return
        self._pending_smart_plan = plans
        blocks = []
        for i, plan in enumerate(plans, 1):
            blocks.append((f"#{i}\n" if len(plans) > 1 else "") + plan.summary(self.tr.language))
        self.smart_preview.setPlainText("\n\n--------------------\n\n".join(blocks))

    def approve_smart_rule(self):
        if self._pending_smart_plan is None:
            self.preview_smart_rule()
            if self._pending_smart_plan is None:
                return
        plans = self._pending_smart_plan if isinstance(self._pending_smart_plan, list) else [self._pending_smart_plan]
        ids = [self.db.add_smart_rule(plan) for plan in plans]
        self.smart_command.clear(); self.smart_preview.clear(); self._pending_smart_plan = None
        label = ", ".join(str(x) for x in ids)
        QMessageBox.information(self, self.tr.t("smart_agent"), self.tr.t("smart_rules_saved", ids=label, count=len(ids)))
        self.refresh_smart_rules()

    def run_smart_rule_now(self):
        rid = self._selected_id(self.smart_rules_table)
        if rid is not None:
            if QMessageBox.question(self, self.tr.t("smart_agent"), self.tr.t("smart_run_confirm", id=rid)) == QMessageBox.Yes:
                self.engine.command("run_smart_rule_now", rid)

    def toggle_smart_rule(self):
        rid = self._selected_id(self.smart_rules_table)
        if rid is not None:
            rule = self.db.get_smart_rule(rid)
            if rule:
                self.db.update_smart_rule_enabled(rid, not bool(rule["enabled"]))
                self.refresh_smart_rules()

    def delete_smart_rule(self):
        rid = self._selected_id(self.smart_rules_table)
        if rid is not None:
            self.db.delete_smart_rule(rid); self.refresh_smart_rules()

    def save_telegram_settings(self):
        try:
            user_id = self.telegram_user_id.text().strip()
            enabled = self.telegram_enabled.isChecked()
            token = self.telegram_token.text().strip()
            if user_id and not user_id.isdigit():
                QMessageBox.warning(self, self.tr.t("telegram_remote"), self.tr.t("telegram_user_numeric")); return
            if token:
                self.security.set_secret("telegram_bot_token", token)
                self.telegram_token.clear()
            if enabled and (not user_id or not self.security.get_secret("telegram_bot_token")):
                QMessageBox.warning(self, self.tr.t("telegram_remote"), self.tr.t("telegram_required")); return
            self.db.set_setting("telegram_authorized_user_id", user_id)
            self.db.set_setting("telegram_enabled", enabled)
            QMessageBox.information(self, self.tr.t("telegram_remote"), self.tr.t("telegram_saved"))
        except Exception as exc:
            QMessageBox.critical(self, self.tr.t("telegram_remote"), str(exc))

    def test_telegram(self):
        self.save_telegram_settings()
        if not bool(self.db.get_setting("telegram_enabled", False)):
            return
        self.telegram_status.setText(self.tr.t("telegram_testing"))
        self.engine.command("telegram_test")

    def add_group(self):
        if not self.g_name.text().strip() or not self.g_url.text().strip(): QMessageBox.warning(self, self.tr.t("facebook_groups"), self.tr.t("name_required")); return
        try:
            self.db.add_group(self.g_name.text(), self.g_url.text(), self.g_tags.text()); self.g_name.clear(); self.g_url.clear(); self.g_tags.clear(); self.refresh_groups()
        except Exception as exc: QMessageBox.critical(self, self.tr.t("facebook_groups"), str(exc))

    def delete_group(self):
        row = self.groups_table.currentRow()
        if row >= 0: self.db.delete_group(int(self.groups_table.item(row, 0).text())); self.refresh_groups()

    def add_campaign(self):
        if not self.c_name.text().strip() or not self.c_page.text().strip(): QMessageBox.warning(self, self.tr.t("facebook_campaigns"), self.tr.t("campaign_required")); return
        self.db.add_campaign(self.c_name.text(), self.c_page.text(), self.c_offset.value(), self.c_keyword.text(), self.c_max.value(), self.c_interval.value(), self.c_days.value(), self.c_time.time().toString("HH:mm"), self.c_prefix.text())
        self.c_name.clear(); self.c_keyword.clear(); self.c_prefix.clear(); self.refresh_campaigns()

    def _selected_id(self, table):
        row = table.currentRow(); return None if row < 0 else int(table.item(row, 0).text())
    def run_campaign_now(self):
        cid = self._selected_id(self.campaign_table)
        if cid is not None: self.engine.command("run_campaign_now", cid)
    def toggle_campaign(self):
        cid = self._selected_id(self.campaign_table)
        if cid is not None:
            c = self.db.get_campaign(cid); self.db.update_campaign_enabled(cid, not bool(c["enabled"])); self.refresh_campaigns()
    def delete_campaign(self):
        cid = self._selected_id(self.campaign_table)
        if cid is not None: self.db.delete_campaign(cid); self.refresh_campaigns()

    def add_wa_contact(self):
        name, phone = self.wa_name.text().strip(), self.wa_phone.text().strip()
        if not name or not phone: QMessageBox.warning(self, self.tr.t("whatsapp"), self.tr.t("contact_required")); return
        if not is_valid_international_phone(phone): QMessageBox.warning(self, self.tr.t("whatsapp"), self.tr.t("invalid_phone")); return
        try:
            self.db.add_wa_contact(name, phone, self.wa_tags.text(), self.wa_optin.isChecked())
            self.wa_name.clear(); self.wa_phone.clear(); self.wa_tags.clear(); self.refresh_wa_contacts()
        except Exception as exc: QMessageBox.critical(self, self.tr.t("whatsapp"), str(exc))

    def delete_wa_contact(self):
        cid = self._selected_id(self.wa_contacts_table)
        if cid is not None: self.db.delete_wa_contact(cid); self.refresh_wa_contacts()

    def import_wa_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, self.tr.t("select_csv"), "", "CSV Files (*.csv);;All Files (*)")
        if not path: return
        count = 0
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = (row.get("name") or row.get("Name") or "").strip()
                    phone = (row.get("phone") or row.get("Phone") or "").strip()
                    tags = (row.get("tags") or row.get("Tags") or "").strip()
                    opt_raw = str(row.get("opt_in") or row.get("OptIn") or "1").strip().casefold()
                    opt_in = opt_raw in {"1", "true", "yes", "y", "نعم"}
                    if name and is_valid_international_phone(phone):
                        self.db.upsert_wa_contact(name, phone, tags, opt_in); count += 1
            QMessageBox.information(self, self.tr.t("import_csv"), self.tr.t("csv_import_done", count=count)); self.refresh_wa_contacts()
        except Exception as exc: QMessageBox.critical(self, self.tr.t("import_csv"), str(exc))

    def preview_wa_batches(self):
        contacts = self.db.list_wa_contacts(enabled_only=True, opted_in_only=True, keyword=self.wac_keyword.text().strip() or None)
        size = self.wac_batch.value(); batches = math.ceil(len(contacts) / size) if contacts else 0
        QMessageBox.information(self, self.tr.t("preview_batches"), self.tr.t("batch_preview_text", contacts=len(contacts), batches=batches, size=size))

    def add_wa_campaign(self):
        name = self.wac_name.text().strip(); mode = self.wac_mode.currentData(); text = self.wac_message.toPlainText().strip(); template = self.wac_template.text().strip()
        if not name or (mode == "text" and not text): QMessageBox.warning(self, self.tr.t("whatsapp"), self.tr.t("wa_campaign_required")); return
        if mode == "template" and not template: QMessageBox.warning(self, self.tr.t("whatsapp"), self.tr.t("wa_template_required")); return
        self.db.add_wa_campaign(name, mode, text, template, self.wac_template_lang.text(), self.wac_keyword.text(), self.wac_batch.value(), self.wac_interval.value(), self.wac_days.value(), self.wac_time.time().toString("HH:mm"))
        self.wac_name.clear(); self.wac_message.clear(); self.wac_template.clear(); self.wac_keyword.clear(); self.refresh_wa_campaigns()

    def run_wa_campaign_now(self):
        cid = self._selected_id(self.wa_campaign_table)
        if cid is not None: self.engine.command("run_wa_campaign_now", cid)
    def toggle_wa_campaign(self):
        cid = self._selected_id(self.wa_campaign_table)
        if cid is not None:
            c = self.db.get_wa_campaign(cid); self.db.update_wa_campaign_enabled(cid, not bool(c["enabled"])); self.refresh_wa_campaigns()
    def delete_wa_campaign(self):
        cid = self._selected_id(self.wa_campaign_table)
        if cid is not None: self.db.delete_wa_campaign(cid); self.refresh_wa_campaigns()

    def save_wa_settings(self):
        try:
            self.db.set_setting("wa_phone_number_id", self.wa_phone_id.text().strip())
            self.db.set_setting("wa_api_version", self.wa_api_version.text().strip() or "v24.0")
            if self.wa_token.text().strip(): self.security.set_secret("wa_access_token", self.wa_token.text().strip()); self.wa_token.clear()
            QMessageBox.information(self, self.tr.t("whatsapp"), self.tr.t("wa_saved"))
        except Exception as exc: QMessageBox.critical(self, self.tr.t("whatsapp"), str(exc))

    def apply_language(self):
        lang = self.lang_combo.currentData() or "en"
        if lang == self.tr.language: return
        self.db.set_setting("language", lang)
        QMessageBox.information(self, self.tr.t("language"), self.tr.t("restart_language"))
        self._really_quit = True
        self.engine.shutdown(); self.engine.join(timeout=3); self.tray.hide()
        if getattr(sys, "frozen", False):
            QProcess.startDetached(sys.executable, sys.argv[1:])
        else:
            QProcess.startDetached(sys.executable, [sys.argv[0], *sys.argv[1:]])
        QApplication.quit()

    def refresh_all(self):
        paused = bool(self.db.get_setting("paused", False)); self.status_label.setText(self.tr.t("paused") if paused else self.tr.t("running")); self.pause_btn.setText(self.tr.t("resume_agent") if paused else self.tr.t("pause_agent"))
        fb_state = self.db.get_setting("facebook_connection_status", "not_checked") or "not_checked"
        fb_key = {
            "connected": "facebook_connected",
            "not_connected": "facebook_not_connected",
            "verification_required": "facebook_verification_required",
            "browser_closed": "facebook_browser_closed",
            "browser_error": "facebook_browser_error",
            "manual_login": "facebook_manual_login",
            "checking": "facebook_checking",
            "profile_in_use": "facebook_profile_in_use",
            "not_checked": "facebook_not_checked",
        }.get(str(fb_state), "facebook_not_checked")
        backend = self.db.get_setting("facebook_browser_backend", "") or ""
        fb_text = self.tr.t(fb_key)

        if fb_state == "manual_login":
            try:
                started = float(self.db.get_setting("facebook_manual_login_started_at", 0) or 0)
            except Exception:
                started = 0
            if started and time.time() - started > 45:
                fb_text = self.tr.t("facebook_login_stalled")

        if backend and fb_state in ("connected", "verification_required", "manual_login"):
            fb_text += f" — {backend}"
        if fb_state in ("browser_error", "profile_in_use"):
            err = str(self.db.get_setting("facebook_browser_last_error", "") or "").strip()
            if err:
                fb_text += f" — {err[:180]}"
        self.fb_status_label.setText(fb_text)
        fb_stats = self.db.queue_stats(); smart_stats = self.db.smart_queue_stats(); wa_stats = self.db.wa_queue_stats()
        parts = ([f"FB {k}: {v}" for k, v in sorted(fb_stats.items())] +
                 [f"SMART {k}: {v}" for k, v in sorted(smart_stats.items())] +
                 [f"WA {k}: {v}" for k, v in sorted(wa_stats.items())])
        self.queue_label.setText(", ".join(parts) or self.tr.t("empty"))
        camps = [c for c in self.db.list_campaigns() if c["enabled"] and c["next_run_at"]]
        self.next_label.setText(min((c["next_run_at"] for c in camps), default="—"))
        srules = [r for r in self.db.list_smart_rules() if r["enabled"] and r["next_run_at"]]
        self.smart_next_label.setText(min((r["next_run_at"] for r in srules), default="—"))
        wcamps = [c for c in self.db.list_wa_campaigns() if c["enabled"] and c["next_run_at"]]
        self.wa_next_label.setText(min((c["next_run_at"] for c in wcamps), default="—"))
        self.refresh_groups(); self.refresh_campaigns(); self.refresh_smart_rules(); self.refresh_wa_contacts(); self.refresh_wa_campaigns(); self.refresh_logs()
        if hasattr(self, "telegram_status"):
            t = self.db.get_setting("telegram_test_status", {}) or {}
            if isinstance(t, dict) and t.get("message"):
                self.telegram_status.setText(str(t.get("message")))

    def refresh_groups(self):
        rows = self.db.list_groups(); self.groups_table.setRowCount(len(rows))
        for r, g in enumerate(rows):
            vals = [g["id"], g["name"], g["url"], g["tags"], self.tr.t("yes") if g["enabled"] else self.tr.t("no")]
            for c, v in enumerate(vals): self.groups_table.setItem(r, c, QTableWidgetItem(str(v)))

        result = self.db.get_setting("facebook_group_discovery_result", {}) or {}
        if not isinstance(result, dict):
            result = {}
        status = str(result.get("status") or "")
        count = int(result.get("count") or 0)
        error = str(result.get("error") or "").strip()
        if hasattr(self, "discover_btn"):
            self.discover_btn.setEnabled(status not in {"queued", "running"})
        if hasattr(self, "group_discovery_status"):
            if status == "queued":
                text = self.tr.t("discover_groups_queued")
            elif status == "running":
                text = self.tr.t("discover_groups_running")
            elif status == "done":
                text = self.tr.t("discover_groups_done").format(count=count)
            elif status == "empty":
                text = self.tr.t("discover_groups_empty")
            elif status == "profile_in_use":
                text = self.tr.t("discover_groups_profile_in_use")
            elif status == "login_required":
                text = self.tr.t("discover_groups_login_required")
            elif status == "checkpoint":
                text = self.tr.t("discover_groups_checkpoint")
            elif status == "error":
                text = self.tr.t("discover_groups_error").format(error=error[:220] or "Unknown error")
            else:
                text = ""
            self.group_discovery_status.setText(text)

    def refresh_campaigns(self):
        rows = self.db.list_campaigns(); self.campaign_table.setRowCount(len(rows))
        for r, c in enumerate(rows):
            vals = [c["id"], c["name"], c["source_page_url"], c["post_offset"], c["group_keyword"], c["max_groups"], c["interval_seconds"], c["cadence_days"], c["run_time"], (c["next_run_at"] or "") + ("" if c["enabled"] else " [OFF]")]
            for col, v in enumerate(vals): self.campaign_table.setItem(r, col, QTableWidgetItem(str(v)))

    def refresh_smart_rules(self):
        if not hasattr(self, "smart_rules_table"):
            return
        rows = self.db.list_smart_rules(); self.smart_rules_table.setRowCount(len(rows))
        for r, rule in enumerate(rows):
            mode = self.tr.t("rotation") if rule["post_mode"] == "rotation" else (self.tr.t("latest_post") if int(rule["post_offset"]) == 0 else f"-{rule['post_offset']}")
            details = str(rule["command_text"] or "")[:180]
            vals = [rule["id"], rule["name"], rule["group_keyword"], mode, rule["run_time"], rule["next_run_at"] or "", self.tr.t("yes") if rule["enabled"] else self.tr.t("no"), details]
            for col, v in enumerate(vals): self.smart_rules_table.setItem(r, col, QTableWidgetItem(str(v)))

    def refresh_wa_contacts(self):
        rows = self.db.list_wa_contacts(); self.wa_contacts_table.setRowCount(len(rows))
        for r, c in enumerate(rows):
            vals = [c["id"], c["name"], c["phone"], c["tags"], self.tr.t("yes") if c["opt_in"] else self.tr.t("no"), self.tr.t("yes") if c["enabled"] else self.tr.t("no")]
            for col, v in enumerate(vals): self.wa_contacts_table.setItem(r, col, QTableWidgetItem(str(v)))

    def refresh_wa_campaigns(self):
        rows = self.db.list_wa_campaigns(); self.wa_campaign_table.setRowCount(len(rows))
        for r, c in enumerate(rows):
            mode = self.tr.t("text_message") if c["message_mode"] == "text" else self.tr.t("template_message")
            vals = [c["id"], c["name"], mode, c["target_keyword"], c["batch_size"], c["interval_seconds"], c["cadence_days"], c["run_time"], (c["next_run_at"] or "") + ("" if c["enabled"] else " [OFF]")]
            for col, v in enumerate(vals): self.wa_campaign_table.setItem(r, col, QTableWidgetItem(str(v)))

    def refresh_logs(self):
        rows = self.db.recent_audit(150); self.logs_table.setRowCount(len(rows))
        for r, x in enumerate(rows):
            event = EVENT_AR.get(x["event"], x["event"]) if self.tr.rtl else x["event"]
            for c, v in enumerate([x["ts"], x["level"], event, x["details"]]): self.logs_table.setItem(r, c, QTableWidgetItem(str(v)))

    def closeEvent(self, event):
        if not self._really_quit:
            self.hide(); self.tray.showMessage(APP_TITLE, "البرنامج ما زال يعمل في شريط ويندوز." if self.tr.rtl else "Agent is still running in the Windows tray.", QSystemTrayIcon.Information, 2500); event.ignore(); return
        self.engine.shutdown(); self.engine.join(timeout=5); self.tray.hide(); event.accept()


def show_splash(app: QApplication, tr: Translator, milliseconds: int = 1100):
    splash = SplashWidget(tr)
    splash.show(); app.processEvents()
    loop = QEventLoop(); QTimer.singleShot(milliseconds, loop.quit); loop.exec()
    splash.close(); app.processEvents()


def run_app():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setWindowIcon(window_icon())
    migrate_legacy_startup()

    db = Database()
    language = db.get_setting("language", "") or ""
    if language not in LANGUAGES:
        chooser = LanguageDialog()
        if chooser.exec() != QDialog.Accepted:
            return
        language = chooser.language
        db.set_setting("language", language)
        db.set_setting("first_run_done", True)

    tr = Translator(language)
    app.setLayoutDirection(Qt.RightToLeft if tr.rtl else Qt.LeftToRight)

    # Splash is intentionally short and always closes BEFORE the PIN dialog.
    show_splash(app, tr, 1100)

    security = SecurityManager(db)
    security.restrict_app_folder_windows()
    pin = PinDialog(security, tr, create=not security.has_pin())
    if pin.exec() != QDialog.Accepted:
        return

    engine = AgentEngine(db, security)
    engine.start()
    win = MainWindow(db, engine, security, tr)
    app.setQuitOnLastWindowClosed(False)
    if "--minimized" not in sys.argv:
        win.show()
    sys.exit(app.exec())
