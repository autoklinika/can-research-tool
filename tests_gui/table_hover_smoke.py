from __future__ import annotations

from PySide6.QtCore import QEvent
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import QApplication, QTableView, QVBoxLayout, QWidget

from gui.table_hover import (
    PASTEL_BLUE_HOVER,
    PASTEL_BLUE_SELECTION,
    SELECTION_TEXT,
    enable_fast_cell_hover,
)


class CaptureHost(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.active = False
        self.layout = QVBoxLayout(self)

    @property
    def is_capturing(self) -> bool:
        return self.active


def main() -> None:
    app = QApplication.instance() or QApplication([])
    host = CaptureHost()
    table = QTableView(host)
    host.layout.addWidget(table)
    model = QStandardItemModel(3, 3, table)
    table.setModel(model)
    host.resize(420, 180)
    host.show()
    app.processEvents()

    delegate = enable_fast_cell_hover(table)
    tracker = table._crt_hover_tracker

    first = model.index(0, 0)
    second = model.index(1, 1)
    tracker.update_from_position(table.visualRect(first).center())
    assert delegate.hovered_index == first

    tracker.update_from_position(table.visualRect(second).center())
    assert delegate.hovered_index == second
    assert delegate.hover_color.name() == PASTEL_BLUE_HOVER.name() == "#dceeff"

    style = table.styleSheet().lower()
    assert PASTEL_BLUE_SELECTION.name() == "#f4faff"
    assert SELECTION_TEXT.name() == "#102033"
    assert "#f4faff" in style
    assert "#102033" in style

    tooltip_event = QEvent(QEvent.Type.ToolTip)
    assert tracker.eventFilter(table.viewport(), tooltip_event) is False
    host.active = True
    assert tracker.tooltips_suppressed() is True
    assert tracker.eventFilter(table.viewport(), tooltip_event) is True
    host.active = False
    assert tracker.tooltips_suppressed() is False

    tracker.clear()
    assert not delegate.hovered_index.isValid()
    host.close()
    app.processEvents()


if __name__ == "__main__":
    main()
