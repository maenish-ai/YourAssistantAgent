from __future__ import annotations

import sys
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QTime
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem,
    QTimeEdit, QVBoxLayout, QWidget, QSystemTrayIcon, QMenu, QSplashScreen, QFrame
)

from .branding import pixmap, splash_path, window_icon
from .db import Database
from .engine import AgentEngine
from .security import SecurityManager
from .startup import (
    is_enabled as startup_is_enabled,
    migrate_legacy_startup,
    set_enabled as startup_set_enabled,
)


APP_TITLE = "Your Assistant Agent"


class BrandBanner(QWidget):
    def __init__(self, title: str = APP_TITLE, subtitle: str = "Smarter posting. Stronger control.", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        logo_label = QLabel()
        logo = pixmap("app_icon.png")
        if not logo.isNull():
            logo_label.setPixmap(logo.scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        lay.addWidget(logo_label)

        txt = QVBoxLayout()
        head = QLabel(title)
        head.setStyleSheet("font-size: 24px; font-weight: 800; color: #1E1B4B;")
        sub = QLabel(subtitle)
        sub.setStyleSheet("font-size: 12px; color: #6B7280;")
        txt.addWidget(head)
        txt.addWidget(sub)
        txt.addStretch(1)
        lay.addLayout(txt, 1)


class PinDialog(QDialog):
    def __init__(self, security: SecurityManager, create=False, parent=None):
        super().__init__(parent)
        self.security = security
        self.create = create
        self.setWindowTitle(f"{APP_TITLE} - Security")
        self.setWindowIcon(window_icon())
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.addWidget(BrandBanner(APP_TITLE, "Secure local access with your private PIN."))

        form = QFormLayout()
        self.pin = QLineEdit()
        self.pin.setEchoMode(QLineEdit.Password)
        form.addRow("PIN:" if not create else "Create PIN:", self.pin)
        self.confirm = None
        if create:
            self.confirm = QLineEdit()
            self.confirm.setEchoMode(QLineEdit.Password)
            form.addRow("Confirm PIN:", self.confirm)
        root.addLayout(form)

        note = QLabel("This PIN protects the agent locally on your Windows device. Facebook password is never requested here.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#6B7280;")
        root.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _accept(self):
        value = self.pin.text()
        if self.create:
            if len(value) < 4:
                QMessageBox.warning(self, "PIN", "Use at least 4 characters.")
                return
            if value != self.confirm.text():
                QMessageBox.warning(self, "PIN", "PIN values do not match.")
                return
            self.security.set_pin(value)
            self.accept()
            return
        if not self.security.verify_pin(value):
            QMessageBox.warning(self, "PIN", "Incorrect PIN.")
            return
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, db: Database, engine: AgentEngine):
        super().__init__()
        self.db = db
        self.engine = engine
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(window_icon())
        self.resize(1180, 760)
        self._really_quit = False
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.dashboard = QWidget()
        self.groups_tab = QWidget()
        self.campaigns_tab = QWidget()
        self.logs_tab = QWidget()
        self.tabs.addTab(self.dashboard, "Dashboard")
        self.tabs.addTab(self.groups_tab, "Groups")
        self.tabs.addTab(self.campaigns_tab, "Campaigns")
        self.tabs.addTab(self.logs_tab, "Audit Log")

        self._build_dashboard()
        self._build_groups()
        self._build_campaigns()
        self._build_logs()
        self._build_tray()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_all)
        self.timer.start(2500)
        self.refresh_all()

    def _build_dashboard(self):
        lay = QVBoxLayout(self.dashboard)
        lay.addWidget(BrandBanner(APP_TITLE, "Local automation controller with persistent branding across startup, window and tray."))

        hero = QLabel()
        brand = pixmap("branding_full.png")
        if not brand.isNull():
            hero.setPixmap(brand.scaledToWidth(430, Qt.SmoothTransformation))
            hero.setAlignment(Qt.AlignLeft)
            lay.addWidget(hero)

        buttons = QHBoxLayout()
        self.login_btn = QPushButton("Open dedicated Facebook browser")
        self.login_btn.clicked.connect(lambda: self.engine.command("open_login"))
        self.pause_btn = QPushButton()
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.kill_btn = QPushButton("EMERGENCY STOP")
        self.kill_btn.setStyleSheet("font-weight:700; padding:8px;")
        self.kill_btn.clicked.connect(self.emergency_stop)
        self.startup_check = QCheckBox("Start with Windows")
        try:
            self.startup_check.setChecked(startup_is_enabled())
        except Exception:
            self.startup_check.setChecked(False)
        self.startup_check.toggled.connect(self.toggle_startup)
        buttons.addWidget(self.login_btn)
        buttons.addWidget(self.pause_btn)
        buttons.addWidget(self.kill_btn)
        buttons.addWidget(self.startup_check)
        lay.addLayout(buttons)

        box = QGroupBox("Status")
        grid = QGridLayout(box)
        self.status_label = QLabel()
        self.queue_label = QLabel()
        self.next_label = QLabel()
        grid.addWidget(QLabel("Agent:"), 0, 0)
        grid.addWidget(self.status_label, 0, 1)
        grid.addWidget(QLabel("Queue:"), 1, 0)
        grid.addWidget(self.queue_label, 1, 1)
        grid.addWidget(QLabel("Next campaign:"), 2, 0)
        grid.addWidget(self.next_label, 2, 1)
        lay.addWidget(box)

        note = QLabel(
            "First use: open the dedicated Facebook browser and sign in manually. "
            "The application never asks for or stores your Facebook password. "
            "If Facebook requests a security checkpoint, the agent pauses automatically."
        )
        note.setWordWrap(True)
        lay.addWidget(note)
        lay.addStretch(1)

    def _build_groups(self):
        lay = QVBoxLayout(self.groups_tab)
        helper = QLabel("Add Facebook groups once, then classify them by area or keyword such as دابوق, صويلح, ألف حرس.")
        helper.setWordWrap(True)
        helper.setStyleSheet("color:#6B7280;")
        lay.addWidget(helper)
        form = QHBoxLayout()
        self.g_name = QLineEdit(); self.g_name.setPlaceholderText("Group name")
        self.g_url = QLineEdit(); self.g_url.setPlaceholderText("https://www.facebook.com/groups/...")
        self.g_tags = QLineEdit(); self.g_tags.setPlaceholderText("Tags / area e.g. دابوق, صويلح")
        add = QPushButton("Add group")
        add.clicked.connect(self.add_group)
        form.addWidget(self.g_name, 2); form.addWidget(self.g_url, 4); form.addWidget(self.g_tags, 2); form.addWidget(add)
        lay.addLayout(form)
        self.groups_table = QTableWidget(0, 5)
        self.groups_table.setHorizontalHeaderLabels(["ID", "Name", "URL", "Tags", "Enabled"])
        self.groups_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lay.addWidget(self.groups_table)
        del_btn = QPushButton("Delete selected group")
        del_btn.clicked.connect(self.delete_group)
        lay.addWidget(del_btn)

    def _build_campaigns(self):
        lay = QVBoxLayout(self.campaigns_tab)
        box = QGroupBox("New campaign")
        form = QFormLayout(box)
        self.c_name = QLineEdit(); self.c_name.setPlaceholderText("مثال: آخر بوست - ألف حرس")
        self.c_page = QLineEdit(); self.c_page.setPlaceholderText("Facebook Page URL")
        self.c_offset = QSpinBox(); self.c_offset.setRange(0, 20); self.c_offset.setToolTip("0 = latest, 1 = previous, 2 = one before that")
        self.c_keyword = QLineEdit(); self.c_keyword.setPlaceholderText("Group name/tag contains...")
        self.c_max = QSpinBox(); self.c_max.setRange(1, 100); self.c_max.setValue(10)
        self.c_interval = QSpinBox(); self.c_interval.setRange(30, 3600); self.c_interval.setValue(60); self.c_interval.setSuffix(" sec")
        self.c_days = QSpinBox(); self.c_days.setRange(1, 365); self.c_days.setValue(3); self.c_days.setSuffix(" days")
        self.c_time = QTimeEdit(); self.c_time.setDisplayFormat("HH:mm"); self.c_time.setTime(QTime(20, 0))
        self.c_prefix = QLineEdit(); self.c_prefix.setPlaceholderText("Optional text before the source post link")
        form.addRow("Campaign name", self.c_name)
        form.addRow("Source page", self.c_page)
        form.addRow("Post offset", self.c_offset)
        form.addRow("Target group keyword/tag", self.c_keyword)
        form.addRow("Maximum groups", self.c_max)
        form.addRow("Delay between groups", self.c_interval)
        form.addRow("Run every", self.c_days)
        form.addRow("At", self.c_time)
        form.addRow("Optional prefix", self.c_prefix)
        add = QPushButton("Create campaign")
        add.clicked.connect(self.add_campaign)
        form.addRow(add)
        lay.addWidget(box)

        self.campaign_table = QTableWidget(0, 10)
        self.campaign_table.setHorizontalHeaderLabels([
            "ID","Name","Page","Offset","Keyword","Max","Delay","Every days","Time","Next run"
        ])
        self.campaign_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.campaign_table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.campaign_table)

        row = QHBoxLayout()
        run = QPushButton("Run selected now")
        run.clicked.connect(self.run_campaign_now)
        toggle = QPushButton("Enable/Disable selected")
        toggle.clicked.connect(self.toggle_campaign)
        delete = QPushButton("Delete selected")
        delete.clicked.connect(self.delete_campaign)
        row.addWidget(run); row.addWidget(toggle); row.addWidget(delete)
        lay.addLayout(row)

    def _build_logs(self):
        lay = QVBoxLayout(self.logs_tab)
        note = QLabel("Audit log records important events, safety actions and execution results.")
        note.setStyleSheet("color:#6B7280;")
        lay.addWidget(note)
        self.logs_table = QTableWidget(0, 4)
        self.logs_table.setHorizontalHeaderLabels(["Time", "Level", "Event", "Details"])
        self.logs_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lay.addWidget(self.logs_table)

    def _build_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setToolTip(APP_TITLE)
        self.tray.setIcon(window_icon())
        menu = QMenu(self)
        show_action = menu.addAction(f"Open {APP_TITLE}")
        show_action.triggered.connect(self.show_normal)
        stop_action = menu.addAction("Emergency stop")
        stop_action.triggered.connect(self.emergency_stop)
        menu.addSeparator()
        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(self.exit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_normal() if reason == QSystemTrayIcon.DoubleClick else None)
        self.tray.show()

    def show_normal(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def exit_app(self):
        self._really_quit = True
        self.close()

    def toggle_startup(self, checked: bool):
        try:
            startup_set_enabled(bool(checked))
            self.db.audit("INFO", "startup_changed", str(bool(checked)))
        except Exception as exc:
            QMessageBox.warning(self, "Startup", str(exc))
            self.startup_check.blockSignals(True)
            self.startup_check.setChecked(False)
            self.startup_check.blockSignals(False)

    def toggle_pause(self):
        self.db.set_setting("paused", not bool(self.db.get_setting("paused", False)))
        self.db.audit("INFO", "agent_pause_toggled", str(self.db.get_setting("paused")))
        self.refresh_all()

    def emergency_stop(self):
        reply = QMessageBox.question(self, "Emergency stop", "Pause the agent and cancel all pending queue items?")
        if reply == QMessageBox.Yes:
            self.db.set_setting("paused", True)
            self.db.clear_pending()
            self.db.audit("SECURITY", "emergency_stop")
            self.refresh_all()

    def add_group(self):
        if not self.g_name.text().strip() or not self.g_url.text().strip():
            QMessageBox.warning(self, "Group", "Name and URL are required.")
            return
        try:
            self.db.add_group(self.g_name.text(), self.g_url.text(), self.g_tags.text())
            self.g_name.clear(); self.g_url.clear(); self.g_tags.clear()
            self.refresh_groups()
        except Exception as exc:
            QMessageBox.critical(self, "Group", str(exc))

    def delete_group(self):
        row = self.groups_table.currentRow()
        if row < 0:
            return
        gid = int(self.groups_table.item(row, 0).text())
        self.db.delete_group(gid)
        self.refresh_groups()

    def add_campaign(self):
        if not self.c_name.text().strip() or not self.c_page.text().strip():
            QMessageBox.warning(self, "Campaign", "Campaign name and source page are required.")
            return
        self.db.add_campaign(
            self.c_name.text(), self.c_page.text(), self.c_offset.value(), self.c_keyword.text(),
            self.c_max.value(), self.c_interval.value(), self.c_days.value(), self.c_time.time().toString("HH:mm"),
            self.c_prefix.text(),
        )
        self.c_name.clear(); self.c_keyword.clear(); self.c_prefix.clear()
        self.refresh_campaigns()

    def _selected_campaign_id(self):
        row = self.campaign_table.currentRow()
        if row < 0:
            return None
        return int(self.campaign_table.item(row, 0).text())

    def run_campaign_now(self):
        cid = self._selected_campaign_id()
        if cid is not None:
            self.engine.command("run_campaign_now", cid)

    def toggle_campaign(self):
        cid = self._selected_campaign_id()
        if cid is None:
            return
        camp = self.db.get_campaign(cid)
        self.db.update_campaign_enabled(cid, not bool(camp["enabled"]))
        self.refresh_campaigns()

    def delete_campaign(self):
        cid = self._selected_campaign_id()
        if cid is None:
            return
        self.db.delete_campaign(cid)
        self.refresh_campaigns()

    def refresh_all(self):
        paused = bool(self.db.get_setting("paused", False))
        self.status_label.setText("PAUSED" if paused else "RUNNING")
        self.pause_btn.setText("Resume agent" if paused else "Pause agent")
        stats = self.db.queue_stats()
        self.queue_label.setText(", ".join(f"{k}: {v}" for k, v in sorted(stats.items())) or "empty")
        camps = self.db.list_campaigns()
        enabled = [c for c in camps if c["enabled"] and c["next_run_at"]]
        self.next_label.setText(min((c["next_run_at"] for c in enabled), default="—"))
        self.refresh_groups(); self.refresh_campaigns(); self.refresh_logs()

    def refresh_groups(self):
        rows = self.db.list_groups()
        self.groups_table.setRowCount(len(rows))
        for r, g in enumerate(rows):
            vals = [g["id"], g["name"], g["url"], g["tags"], "Yes" if g["enabled"] else "No"]
            for c, v in enumerate(vals):
                self.groups_table.setItem(r, c, QTableWidgetItem(str(v)))

    def refresh_campaigns(self):
        rows = self.db.list_campaigns()
        self.campaign_table.setRowCount(len(rows))
        for r, c in enumerate(rows):
            vals = [c["id"], c["name"], c["source_page_url"], c["post_offset"], c["group_keyword"], c["max_groups"],
                    c["interval_seconds"], c["cadence_days"], c["run_time"], (c["next_run_at"] or "") + ("" if c["enabled"] else " [DISABLED]")]
            for col, v in enumerate(vals):
                self.campaign_table.setItem(r, col, QTableWidgetItem(str(v)))

    def refresh_logs(self):
        rows = self.db.recent_audit(150)
        self.logs_table.setRowCount(len(rows))
        for r, x in enumerate(rows):
            for c, v in enumerate([x["ts"], x["level"], x["event"], x["details"]]):
                self.logs_table.setItem(r, c, QTableWidgetItem(str(v)))

    def closeEvent(self, event):
        if not self._really_quit:
            self.hide()
            self.tray.showMessage(APP_TITLE, "Agent is still running in the Windows tray.", QSystemTrayIcon.Information, 2500)
            event.ignore()
            return
        self.engine.shutdown()
        self.engine.join(timeout=5)
        self.tray.hide()
        event.accept()


def show_splash(app: QApplication):
    splash_pm = pixmap("splash.png")
    if splash_pm.isNull():
        return None
    splash = QSplashScreen(splash_pm.scaledToWidth(620, Qt.SmoothTransformation))
    splash.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    splash.showMessage("Initializing Your Assistant Agent...", Qt.AlignBottom | Qt.AlignHCenter, Qt.darkGray)
    splash.show()
    app.processEvents()
    return splash


def run_app():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setWindowIcon(window_icon())
    migrate_legacy_startup()
    db = Database()
    security = SecurityManager(db)
    security.restrict_app_folder_windows()

    splash = show_splash(app)

    pin = PinDialog(security, create=not security.has_pin())
    if pin.exec() != QDialog.Accepted:
        if splash is not None:
            splash.close()
        return

    engine = AgentEngine(db)
    engine.start()
    win = MainWindow(db, engine)
    app.setQuitOnLastWindowClosed(False)
    if splash is not None:
        splash.finish(win)
    if "--minimized" not in sys.argv:
        win.show()
    sys.exit(app.exec())
