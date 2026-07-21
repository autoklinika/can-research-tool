from __future__ import annotations

import time

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QTableView, QWidget, QVBoxLayout

from gui.application_container import ApplicationContainer
from gui.log_search_window import LogSearchWindow


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("AutoklinikaTests")
    app.setApplicationName("CRTLogSearchSmoke")
    QSettings().clear()

    window = ApplicationContainer().create_main_window()
    assert window.search_action.shortcut().toString() == "Ctrl+F"

    page = QWidget()
    layout = QVBoxLayout(page)
    table = QTableView(page)
    table.setObjectName("searchFixtureTable")
    model = QStandardItemModel(3, 2, table)
    values = (
        ("18DA00F9", "27 07"),
        ("18DAF900", "67 07 12 34 56 78"),
        ("18DAF900", "7F 27 35"),
    )
    for row, columns in enumerate(values):
        for column, value in enumerate(columns):
            model.setItem(row, column, QStandardItem(value))
    table.setModel(model)
    layout.addWidget(table)
    window.tabs.addTab(page, "Search fixture")
    window.tabs.setCurrentWidget(page)
    window.show()
    app.processEvents()

    window.search_action.trigger()
    app.processEvents()
    search = window.findChild(LogSearchWindow, "logSearchWindow")
    assert search is not None
    assert search._target_table is table

    search.query_edit.setText("18DAF900")
    search.start_search()
    deadline = time.monotonic() + 3.0
    while search.results.count() != 2 and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert search.results.count() == 2
    assert table.currentIndex().row() == 1

    search.results.setFocus()
    QTest.keyClick(search.results, Qt.Key_N)
    app.processEvents()
    assert table.currentIndex().row() == 2

    QTest.keyClick(search.results, Qt.Key_V)
    app.processEvents()
    assert table.currentIndex().row() == 1

    # Navigation remains active after the user clicks the source table.
    table.setFocus()
    QTest.keyClick(table, Qt.Key_N)
    app.processEvents()
    assert table.currentIndex().row() == 2

    # Typing in the query field must not trigger result navigation.
    search.query_edit.setFocus()
    search.query_edit.clear()
    QTest.keyClicks(search.query_edit, "NV")
    app.processEvents()
    assert search.query_edit.text() == "NV"
    assert table.currentIndex().row() == 2

    search.close()
    window.close()
    app.processEvents()


if __name__ == "__main__":
    main()
