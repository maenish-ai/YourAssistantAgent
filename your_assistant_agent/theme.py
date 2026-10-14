from __future__ import annotations

from PySide6.QtGui import QFont


def apply_modern_theme(app) -> None:
    """Bright modern Qt theme without external theme dependencies."""
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(r'''
QWidget {
    background: #F6F8FF;
    color: #172033;
    font-family: "Segoe UI";
    font-size: 10pt;
}
QMainWindow, QDialog { background: #F6F8FF; }
QTabWidget::pane {
    border: 1px solid #DDE3F5;
    border-radius: 14px;
    top: -1px;
    background: #FFFFFF;
    padding: 8px;
}
QTabBar::tab {
    background: #EEF1FF;
    color: #59627A;
    border: 1px solid #DDE3F5;
    border-bottom: none;
    padding: 11px 16px;
    margin-right: 3px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    font-weight: 650;
}
QTabBar::tab:selected {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #6D5DFB, stop:1 #3F8CFF);
    color: white;
    border-color: #6D5DFB;
}
QTabBar::tab:hover:!selected { background: #E4E9FF; color: #3B46A8; }
QGroupBox {
    background: #FFFFFF;
    border: 1px solid #DDE3F5;
    border-radius: 14px;
    margin-top: 14px;
    padding: 14px 10px 10px 10px;
    font-weight: 700;
    color: #273169;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 7px;
    background: #FFFFFF;
}
QPushButton {
    min-height: 32px;
    padding: 6px 14px;
    border: none;
    border-radius: 9px;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #6757F5, stop:1 #4A7FFF);
    color: white;
    font-weight: 700;
}
QPushButton:hover { background: #5546E8; }
QPushButton:pressed { background: #4337BE; }
QPushButton:disabled { background: #C9CEE0; color: #7A8195; }
QLineEdit, QTextEdit, QComboBox, QSpinBox, QTimeEdit {
    background: #FBFCFF;
    border: 1px solid #CCD4EB;
    border-radius: 9px;
    padding: 7px;
    selection-background-color: #6757F5;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QTimeEdit:focus {
    border: 2px solid #6D5DFB;
    background: white;
}
QTableWidget {
    background: white;
    alternate-background-color: #F7F8FE;
    border: 1px solid #DDE3F5;
    border-radius: 10px;
    gridline-color: #EEF1F7;
}
QHeaderView::section {
    background: #EDEFFF;
    color: #353D77;
    padding: 8px;
    border: none;
    border-right: 1px solid #D8DDEF;
    font-weight: 700;
}
QCheckBox { spacing: 7px; }
QCheckBox::indicator { width: 18px; height: 18px; }
QCheckBox::indicator:checked {
    background: #6757F5;
    border: 2px solid #6757F5;
    border-radius: 4px;
}
QMenu {
    background: white;
    border: 1px solid #DDE3F5;
    border-radius: 8px;
    padding: 5px;
}
QMenu::item { padding: 7px 22px; border-radius: 6px; }
QMenu::item:selected { background: #ECEAFF; color: #4939CF; }
QScrollBar:vertical { background:#F0F2FA; width:11px; margin:0; border-radius:5px; }
QScrollBar::handle:vertical { background:#B8C0DD; min-height:30px; border-radius:5px; }
QScrollBar::handle:vertical:hover { background:#857AF0; }
QToolTip { background:#202646; color:white; border:0; padding:6px; }
''')
