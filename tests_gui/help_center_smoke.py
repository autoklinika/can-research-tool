from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from gui.application_container import ApplicationContainer
from gui.help_center_shell import HelpCenterMainWindow
from gui.help_center_view import HelpCenterWidget


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("AutoklinikaTests")
    app.setApplicationName("CRTHelpCenterSmoke")
    QSettings().clear()

    window = ApplicationContainer().create_main_window()
    assert isinstance(window, HelpCenterMainWindow)
    window.show()
    _drain(app)

    assert window.help_action.shortcut().toString() == "F1"
    assert window.help_menu.title() == "Pomoc"
    assert window.project is None

    initial_count = window.tabs.count()
    window.help_action.trigger()
    _drain(app)

    help_view = window.navigator.widget("help-center")
    assert isinstance(help_view, HelpCenterWidget)
    assert window.tabs.count() == initial_count + 1
    assert "Pomoc CAN Research Tool" in help_view.browser.toPlainText()
    assert len(help_view.visible_topic_ids) >= 25

    help_view.search_edit.setText("jitter percentyl")
    _drain(app)
    assert "timing-jitter" in help_view.visible_topic_ids
    assert "percentiles" in help_view.visible_topic_ids

    help_view.open_topic("uds-transactions")
    _drain(app)
    assert help_view.current_topic_id == "uds-transactions"
    content = help_view.browser.toPlainText()
    assert "Eksplorator transakcji UDS" in content
    assert "nowsze puste artefakty" in content.casefold()
    assert "evidence_truncated" in content

    help_view.open_topic("source-of-truth")
    _drain(app)
    assert help_view.back_button.isEnabled()
    help_view.go_back()
    _drain(app)
    assert help_view.current_topic_id == "uds-transactions"
    help_view.go_forward()
    _drain(app)
    assert help_view.current_topic_id == "source-of-truth"

    window.help_glossary_action.trigger()
    _drain(app)
    same_view = window.navigator.widget("help-center")
    assert same_view is help_view
    assert help_view.current_topic_id == "glossary"
    assert window.tabs.count() == initial_count + 1

    window.help_shortcuts_action.trigger()
    _drain(app)
    assert help_view.current_topic_id == "shortcuts"
    assert "F1" in help_view.browser.toPlainText()

    window.close()
    _drain(app)


def _drain(app: QApplication, cycles: int = 12) -> None:
    for _ in range(cycles):
        app.processEvents()


if __name__ == "__main__":
    main()
