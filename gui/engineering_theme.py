from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication


ENGINEERING_IDE_QSS = r"""
QMainWindow,
QDialog {
    background: #15191d;
}

QLabel,
QCheckBox,
QRadioButton {
    background: transparent;
}

QMenuBar {
    background: #171b1f;
    border-bottom: 1px solid #32383f;
    padding: 2px 4px;
}
QMenuBar::item {
    padding: 5px 9px;
    background: transparent;
}
QMenuBar::item:selected {
    background: #252b31;
}
QMenu {
    background: #1c2126;
    border: 1px solid #3a4149;
    padding: 4px;
}
QMenu::item {
    padding: 6px 28px 6px 24px;
}
QMenu::item:selected {
    background: #26445f;
    color: #ffffff;
}
QMenu::separator {
    height: 1px;
    background: #343b42;
    margin: 4px 7px;
}

QToolBar {
    background: #1b2025;
    border: 0;
    border-bottom: 1px solid #343b42;
    spacing: 3px;
    padding: 4px 5px;
}
QToolBar::separator {
    background: #3a4149;
    width: 1px;
    height: 24px;
    margin: 3px 6px;
}
QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 2px;
    padding: 5px 7px;
}
QToolButton:hover {
    background: #262d34;
    border-color: #3d4751;
}
QToolButton:pressed,
QToolButton:checked {
    background: #24435c;
    border-color: #3879a8;
}
QToolButton:disabled {
    color: #626b74;
}
QToolBar#primaryToolBar {
    min-height: 34px;
}
QLabel#toolbarProjectContext {
    color: #aeb6bf;
    padding: 0 10px;
}
QLabel#captureIndicator {
    border-left: 1px solid #394047;
    padding: 3px 11px;
    min-width: 82px;
    font-weight: 700;
}
QLabel#captureIndicator[state="stopped"] {
    color: #9ba4ae;
}
QLabel#captureIndicator[state="running"] {
    color: #8dd39a;
    background: #183324;
}
QLabel#captureIndicator[state="connecting"] {
    color: #e1bf70;
    background: #352c19;
}
QLabel#captureIndicator[state="error"] {
    color: #f08b8b;
    background: #3b2023;
}

QDockWidget {
    color: #e3e7eb;
    border: 1px solid #30363d;
}
QDockWidget::title {
    background: #20262c;
    border-bottom: 1px solid #363d45;
    padding: 5px 7px;
    text-align: left;
    font-weight: 700;
}
QDockWidget::close-button,
QDockWidget::float-button {
    background: transparent;
    border: 0;
    padding: 2px;
}
QDockWidget::close-button:hover,
QDockWidget::float-button:hover {
    background: #343c44;
}

QTreeView,
QTableView,
QTableWidget,
QListView,
QListWidget,
QPlainTextEdit,
QTextEdit {
    background: #171b1f;
    alternate-background-color: #1c2126;
    border: 1px solid #353c43;
    gridline-color: #30363d;
    selection-background-color: #244b69;
    selection-color: #ffffff;
    outline: 0;
}
QTreeView::item,
QListView::item,
QListWidget::item {
    min-height: 22px;
    padding: 1px 3px;
}
QTreeView::item:hover,
QListView::item:hover,
QListWidget::item:hover {
    background: #232b32;
}
QTreeView::item:selected,
QListView::item:selected,
QListWidget::item:selected {
    background: #244b69;
    color: #ffffff;
}
QTableView::item:selected,
QTableWidget::item:selected {
    background: #244b69;
    color: #ffffff;
}
QHeaderView::section {
    background: #252b31;
    color: #dce1e6;
    border: 0;
    border-right: 1px solid #394149;
    border-bottom: 1px solid #414952;
    padding: 5px 7px;
    font-weight: 700;
}
QHeaderView::section:hover {
    background: #2b333a;
}
QTableCornerButton::section {
    background: #252b31;
    border: 0;
    border-right: 1px solid #394149;
    border-bottom: 1px solid #414952;
}

QTabWidget::pane {
    border: 1px solid #353c43;
    background: #171b1f;
    top: -1px;
}
QTabBar::tab {
    background: #1d2227;
    color: #bfc6cd;
    border: 1px solid #343b42;
    border-bottom: 0;
    padding: 6px 12px;
    min-width: 82px;
}
QTabBar::tab:selected {
    background: #242a30;
    color: #ffffff;
    border-bottom: 2px solid #3fa9e8;
    padding-bottom: 4px;
}
QTabBar::tab:hover:!selected {
    background: #252c33;
    color: #ffffff;
}
QTabBar::close-button {
    margin-left: 5px;
}

QStatusBar {
    background: #171b1f;
    border-top: 1px solid #343b42;
}
QStatusBar QLabel {
    padding: 2px 8px;
}
QStatusBar QLabel#captureStatus {
    font-weight: 700;
}

QGroupBox {
    background: #1b2025;
    border: 1px solid #353c43;
    margin-top: 10px;
    padding-top: 8px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 5px;
    color: #dce1e6;
}

QPushButton {
    background: #252b31;
    color: #e3e7eb;
    border: 1px solid #414952;
    border-radius: 2px;
    padding: 5px 10px;
    min-height: 20px;
}
QPushButton:hover {
    background: #2c343b;
    border-color: #566572;
}
QPushButton:pressed,
QPushButton:checked {
    background: #24435c;
    border-color: #3c82b5;
}
QPushButton:disabled {
    color: #68717a;
    background: #20252a;
    border-color: #30363d;
}

QLineEdit,
QComboBox,
QSpinBox,
QDoubleSpinBox,
QDateEdit,
QTimeEdit,
QDateTimeEdit {
    background: #15191d;
    color: #e5e8eb;
    border: 1px solid #414952;
    border-radius: 2px;
    padding: 4px 6px;
    min-height: 20px;
    selection-background-color: #2d638b;
}
QLineEdit:focus,
QComboBox:focus,
QSpinBox:focus,
QDoubleSpinBox:focus,
QDateEdit:focus,
QTimeEdit:focus,
QDateTimeEdit:focus {
    border-color: #3fa9e8;
}
QComboBox::drop-down {
    border: 0;
    width: 22px;
}
QComboBox QAbstractItemView {
    background: #1b2025;
    border: 1px solid #414952;
    selection-background-color: #244b69;
}

QCheckBox,
QRadioButton {
    spacing: 6px;
}
QCheckBox::indicator,
QRadioButton::indicator {
    width: 14px;
    height: 14px;
}
QCheckBox::indicator:unchecked {
    background: #15191d;
    border: 1px solid #515b65;
}
QCheckBox::indicator:checked {
    background: #2f86bd;
    border: 1px solid #55b7ef;
}
QRadioButton::indicator:unchecked {
    background: #15191d;
    border: 1px solid #515b65;
    border-radius: 7px;
}
QRadioButton::indicator:checked {
    background: #3fa9e8;
    border: 3px solid #1b2025;
    border-radius: 7px;
}

QProgressBar {
    background: #161a1e;
    color: #ffffff;
    border: 1px solid #3c444c;
    border-radius: 2px;
    text-align: center;
    min-height: 18px;
}
QProgressBar::chunk {
    background: #2d9344;
    border-radius: 1px;
}

QWidget#storedLogicalWorkspace {
    background: #1a1e22;
}
QFrame#logicalFilterSection,
QFrame#logicalLoadingSection {
    background: #1b2025;
    border: 1px solid #343b42;
}
QLabel#logicalSectionTitle {
    background: #20252a;
    color: #e1e5e9;
    border: 0;
    border-bottom: 1px solid #343b42;
    padding: 5px 7px;
    min-height: 17px;
    font-size: 10px;
    font-weight: 700;
}
QWidget#logicalSectionBody {
    background: #1b2025;
}
QWidget#logicalSectionBody QLabel {
    color: #d7dce1;
}
QWidget#logicalSectionBody QLineEdit,
QWidget#logicalSectionBody QComboBox {
    min-height: 18px;
    max-height: 26px;
    padding: 3px 6px;
}
QWidget#logicalSectionBody QPushButton {
    min-height: 18px;
    max-height: 27px;
    padding: 3px 12px;
}
QProgressBar#logicalLoadProgress {
    min-height: 20px;
    max-height: 20px;
    border: 1px solid #334039;
    background: #182019;
}
QProgressBar#logicalLoadProgress::chunk {
    background: #438f3f;
}
QLabel#logicalLoadStatus {
    color: #b8bec5;
    border-bottom: 1px solid #59616a;
    padding: 1px 3px;
}
QTableView#storedLogicalMessageTable {
    background: #1a1e22;
    alternate-background-color: #1d2227;
    border: 1px solid #343b42;
    gridline-color: #343a40;
    selection-background-color: #244b69;
    selection-color: #ffffff;
}
QTableView#storedLogicalMessageTable::item {
    padding: 3px 7px;
    border: 0;
}
QTableView#storedLogicalMessageTable::item:hover {
    background: #222a31;
}
QTableView#storedLogicalMessageTable QHeaderView::section {
    background: #262c32;
    color: #e3e7eb;
    border-right: 1px solid #343b42;
    border-bottom: 1px solid #3c444c;
    padding: 5px 7px;
    font-weight: 500;
}

QScrollBar:vertical {
    background: #171b1f;
    width: 12px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #414a53;
    min-height: 28px;
    border-radius: 5px;
    margin: 2px;
}
QScrollBar::handle:vertical:hover {
    background: #56616c;
}
QScrollBar:horizontal {
    background: #171b1f;
    height: 12px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #414a53;
    min-width: 28px;
    border-radius: 5px;
    margin: 2px;
}
QScrollBar::handle:horizontal:hover {
    background: #56616c;
}
QScrollBar::add-line,
QScrollBar::sub-line,
QScrollBar::add-page,
QScrollBar::sub-page {
    background: transparent;
    border: 0;
}

QSplitter::handle {
    background: #343b42;
}
QSplitter::handle:horizontal {
    width: 1px;
}
QSplitter::handle:vertical {
    height: 1px;
}
QSplitter::handle:hover {
    background: #3fa9e8;
}

QFrame#overviewHeader {
    background: #20262c;
    border-bottom: 1px solid #394149;
}
QLabel#projectOverviewTitle {
    color: #ffffff;
    font-weight: 700;
    font-size: 14px;
}
QLabel#secondaryText {
    color: #98a2ac;
}
QTableWidget#recentSessionsTable {
    background: #171b1f;
}

QToolTip {
    background: #252b31;
    color: #f0f2f4;
    border: 1px solid #4a545e;
    padding: 4px;
}
"""


def _engineering_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#15191d"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#e3e7eb"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#171b1f"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#1c2126"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#252b31"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#f0f2f4"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#e3e7eb"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#252b31"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#e3e7eb"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#244b69"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Link, QColor("#55b7ef"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#707a84"))

    disabled = QPalette.ColorGroup.Disabled
    palette.setColor(disabled, QPalette.ColorRole.WindowText, QColor("#68717a"))
    palette.setColor(disabled, QPalette.ColorRole.Text, QColor("#68717a"))
    palette.setColor(disabled, QPalette.ColorRole.ButtonText, QColor("#68717a"))
    palette.setColor(disabled, QPalette.ColorRole.Highlight, QColor("#30363d"))
    palette.setColor(disabled, QPalette.ColorRole.HighlightedText, QColor("#7b858f"))
    return palette


def apply_engineering_theme(app: QApplication) -> None:
    """Install the CRT dark workbench theme over the native platform style."""

    # Keep the native Qt/Windows renderer. Fusion is deliberately not installed:
    # large item views remain faster and Windows-native startup stays stable.
    font = QFont(app.font())
    if font.pointSize() < 9:
        font.setPointSize(9)
    app.setFont(font)
    app.setPalette(_engineering_palette())
    app.setStyleSheet(ENGINEERING_IDE_QSS)
