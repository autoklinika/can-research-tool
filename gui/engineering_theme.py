from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

ENGINEERING_IDE_QSS = r"""
QWidget {
    color: #20242a;
    background-color: #f3f4f6;
}
QMainWindow {
    background-color: #eef0f2;
}
QLabel,
QCheckBox,
QRadioButton {
    background: transparent;
}
QMenuBar {
    background: #f6f7f8;
    border-bottom: 1px solid #c9cdd2;
    padding: 1px;
}
QMenuBar::item {
    padding: 4px 8px;
    background: transparent;
}
QMenuBar::item:selected {
    background: #dfe8f4;
}
QMenu {
    background: #ffffff;
    border: 1px solid #b8bdc4;
    padding: 3px;
}
QMenu::item {
    padding: 5px 24px 5px 24px;
}
QMenu::item:selected {
    background: #dce9f8;
    color: #17202a;
}
QToolBar {
    background: #f6f7f8;
    border: 0;
    border-bottom: 1px solid #c9cdd2;
    spacing: 2px;
    padding: 2px;
}
QToolBar::separator {
    background: #c9cdd2;
    width: 1px;
    height: 22px;
    margin: 4px 5px;
}
QToolButton {
    background: transparent;
    border: 1px solid transparent;
    padding: 4px 6px;
}
QToolButton:hover {
    background: #e5ebf3;
    border-color: #c4cfdd;
}
QToolButton:pressed,
QToolButton:checked {
    background: #d5e3f3;
    border-color: #9fb5cf;
}
QToolBar#activityBar {
    background: #e8eaed;
    border-right: 1px solid #c2c6cc;
    border-bottom: 0;
    padding: 2px;
}
QToolBar#activityBar QToolButton {
    min-width: 38px;
    min-height: 38px;
    padding: 3px;
}
QToolBar#primaryToolBar {
    min-height: 32px;
}
QLabel#toolbarProjectContext {
    color: #4b535d;
    padding: 0 8px;
}
QLabel#captureIndicator {
    border-left: 1px solid #c9cdd2;
    padding: 2px 10px;
    min-width: 78px;
    font-weight: 600;
}
QLabel#captureIndicator[state="stopped"] {
    color: #5c636b;
}
QLabel#captureIndicator[state="running"] {
    color: #176b35;
    background: #e5f4ea;
}
QLabel#captureIndicator[state="connecting"] {
    color: #8a5a00;
    background: #fff4d6;
}
QLabel#captureIndicator[state="error"] {
    color: #a32121;
    background: #fbe8e8;
}
QDockWidget {
    color: #30363d;
    font-weight: 600;
}
QDockWidget::title {
    background: #e8eaed;
    border: 1px solid #c6cad0;
    padding: 4px 6px;
    text-align: left;
}
QTreeView,
QTableView,
QTableWidget,
QListView,
QListWidget,
QPlainTextEdit,
QTextEdit {
    background: #ffffff;
    alternate-background-color: #f7f8fa;
    border: 1px solid #c8ccd1;
    selection-background-color: #cfe2f7;
    selection-color: #16202a;
}
QTreeView::item,
QListView::item {
    min-height: 22px;
}
QTreeView::item:hover,
QListView::item:hover {
    background: #eaf1f9;
}
QHeaderView::section {
    background: #e9ebee;
    border: 0;
    border-right: 1px solid #c7cbd0;
    border-bottom: 1px solid #bfc4ca;
    padding: 4px 6px;
    font-weight: 600;
}
QTabWidget::pane {
    border: 1px solid #c5c9ce;
    background: #ffffff;
}
QTabBar::tab {
    background: #e3e5e8;
    border: 1px solid #c4c8cd;
    border-bottom: 0;
    padding: 5px 10px;
    min-width: 76px;
}
QTabBar::tab:selected {
    background: #ffffff;
    border-top: 2px solid #3c78b5;
    padding-top: 4px;
}
QTabBar::tab:hover:!selected {
    background: #edf1f5;
}
QStatusBar {
    background: #e7e9ec;
    border-top: 1px solid #c3c7cc;
}
QStatusBar QLabel {
    padding: 1px 7px;
}
QStatusBar QLabel#captureStatus {
    font-weight: 700;
}
QGroupBox {
    background: #ffffff;
    border: 1px solid #c8ccd1;
    margin-top: 8px;
    padding-top: 6px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 7px;
    padding: 0 4px;
    font-weight: 600;
}
QPushButton {
    background: #f6f7f8;
    border: 1px solid #b8bdc4;
    padding: 4px 9px;
    min-height: 20px;
}
QPushButton:hover {
    background: #e8eef6;
    border-color: #9aaec5;
}
QPushButton:pressed {
    background: #d8e4f2;
}
QPushButton:disabled {
    color: #90969d;
    background: #eceeef;
    border-color: #d2d5d8;
}
QLineEdit,
QComboBox,
QSpinBox,
QDoubleSpinBox {
    background: #ffffff;
    border: 1px solid #b9bec4;
    padding: 3px 5px;
    min-height: 20px;
}
QLineEdit:focus,
QComboBox:focus,
QSpinBox:focus,
QDoubleSpinBox:focus {
    border-color: #4b82bd;
}
QFrame#projectExplorerHeader,
QFrame#overviewHeader {
    background: #eef0f2;
    border-bottom: 1px solid #c8ccd1;
}
QLabel#projectExplorerName,
QLabel#projectOverviewTitle {
    font-weight: 700;
    font-size: 14px;
}
QLabel#secondaryText {
    color: #69717a;
}
QTableWidget#recentSessionsTable {
    background: #ffffff;
}
QSplitter::handle {
    background: #c9cdd2;
}
QSplitter::handle:horizontal {
    width: 1px;
}
QSplitter::handle:vertical {
    height: 1px;
}
"""


def apply_engineering_theme(app: QApplication) -> None:
    """Install the compact, neutral CRT engineering-workbench theme."""

    app.setStyle("Fusion")
    font = QFont(app.font())
    if font.pointSize() < 9:
        font.setPointSize(9)
    app.setFont(font)
    app.setStyleSheet(ENGINEERING_IDE_QSS)
