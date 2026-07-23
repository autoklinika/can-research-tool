from __future__ import annotations

from enum import StrEnum

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from .engineering_theme import ENGINEERING_IDE_QSS, apply_engineering_theme


THEME_SETTINGS_KEY = "ui/colorTheme"


class ColorTheme(StrEnum):
    DAY = "day"
    NIGHT = "night"


DAY_ENGINEERING_QSS = r"""
QMainWindow, QDialog, QWidget {
    background: #f3f5f7;
    color: #20252a;
}
QMenuBar, QToolBar, QStatusBar {
    background: #e8ebee;
    color: #20252a;
    border-color: #c8cdd2;
}
QMenuBar { border-bottom: 1px solid #c8cdd2; }
QMenuBar::item:selected, QToolButton:hover { background: #dce5ed; }
QMenu {
    background: #ffffff;
    color: #20252a;
    border: 1px solid #bcc3ca;
}
QMenu::item:selected {
    background: #d7eaf7;
    color: #102b3d;
}
QToolBar { border-bottom: 1px solid #c8cdd2; spacing: 3px; padding: 4px 5px; }
QToolButton { background: transparent; border: 1px solid transparent; padding: 5px 7px; }
QToolButton:pressed, QToolButton:checked { background: #cfe3f1; border-color: #7ca9c7; }
QDockWidget { color: #20252a; border: 1px solid #c8cdd2; }
QDockWidget::title, QWidget#projectDockTitleBar {
    background: #e7eaed;
    border-bottom: 1px solid #c8cdd2;
    padding: 5px 7px;
    font-weight: 700;
}
QTreeView, QTableView, QTableWidget, QListView, QListWidget,
QPlainTextEdit, QTextEdit {
    background: #ffffff;
    alternate-background-color: #f4f6f8;
    color: #20252a;
    border: 1px solid #c8cdd2;
    gridline-color: #d6dadd;
    selection-background-color: #cfe7f7;
    selection-color: #102b3d;
    outline: 0;
}
QTreeView::item:hover, QListView::item:hover, QListWidget::item:hover,
QTableView::item:hover { background: #eaf3f9; }
QHeaderView::section {
    background: #e8ebee;
    color: #20252a;
    border: 0;
    border-right: 1px solid #c8cdd2;
    border-bottom: 1px solid #bcc3ca;
    padding: 5px 7px;
    font-weight: 700;
}
QTabWidget::pane { border: 1px solid #c8cdd2; background: #ffffff; top: -1px; }
QTabBar::tab {
    background: #e8ebee;
    color: #4d555d;
    border: 1px solid #c8cdd2;
    border-bottom: 0;
    padding: 6px 12px;
    min-width: 82px;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #101418;
    border-bottom: 2px solid #2786bd;
    padding-bottom: 4px;
}
QGroupBox {
    background: #f8f9fa;
    border: 1px solid #c8cdd2;
    margin-top: 10px;
    padding-top: 8px;
    font-weight: 600;
}
QPushButton {
    background: #e8ebee;
    color: #20252a;
    border: 1px solid #b8bec4;
    border-radius: 2px;
    padding: 5px 10px;
    min-height: 20px;
}
QPushButton:hover { background: #dde5eb; border-color: #88949e; }
QPushButton:pressed, QPushButton:checked { background: #cfe3f1; border-color: #6f9fbe; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit {
    background: #ffffff;
    color: #20252a;
    border: 1px solid #b8bec4;
    border-radius: 2px;
    padding: 4px 6px;
    min-height: 20px;
    selection-background-color: #b9dcef;
}
QComboBox QAbstractItemView { background: #ffffff; color: #20252a; }
QCheckBox::indicator:unchecked, QRadioButton::indicator:unchecked {
    background: #ffffff;
    border: 1px solid #8f989f;
}
QCheckBox::indicator:checked { background: #2786bd; border: 1px solid #176b99; }
QProgressBar { background: #ffffff; color: #20252a; border: 1px solid #b8bec4; text-align: center; }
QProgressBar::chunk { background: #56a568; }
QScrollBar:vertical, QScrollBar:horizontal { background: #edf0f2; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal { background: #b8c0c7; border-radius: 5px; margin: 2px; }
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page { background: transparent; border: 0; }
QSplitter::handle { background: #c8cdd2; }
QToolTip { background: #fffff0; color: #20252a; border: 1px solid #8f989f; padding: 4px; }
QLabel#secondaryText { color: #65717b; }
QLabel#projectOverviewTitle { color: #15191d; font-weight: 700; }
"""


def normalize_theme(value: object) -> ColorTheme:
    try:
        return ColorTheme(str(value).strip().lower())
    except ValueError:
        return ColorTheme.NIGHT


def current_theme(settings: QSettings | None = None) -> ColorTheme:
    source = settings or QSettings()
    return normalize_theme(source.value(THEME_SETTINGS_KEY, ColorTheme.NIGHT.value, str))


def _day_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#f3f5f7"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#20252a"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#f4f6f8"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#fffff0"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#20252a"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#20252a"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#e8ebee"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#20252a"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#000000"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#cfe7f7"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#102b3d"))
    palette.setColor(QPalette.ColorRole.Link, QColor("#176b99"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#737d86"))
    return palette


def apply_color_theme(
    app: QApplication,
    theme: ColorTheme | str,
    *,
    persist: bool = False,
    settings: QSettings | None = None,
) -> ColorTheme:
    selected = normalize_theme(theme)
    font = QFont(app.font())
    if font.pointSize() < 9:
        font.setPointSize(9)
    app.setFont(font)

    if selected is ColorTheme.DAY:
        app.setPalette(_day_palette())
        app.setStyleSheet(DAY_ENGINEERING_QSS)
    else:
        apply_engineering_theme(app)

    if persist:
        target = settings or QSettings()
        target.setValue(THEME_SETTINGS_KEY, selected.value)
        target.sync()
    return selected


def apply_saved_theme(app: QApplication, settings: QSettings | None = None) -> ColorTheme:
    return apply_color_theme(app, current_theme(settings), persist=False, settings=settings)
