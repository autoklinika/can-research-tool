from __future__ import annotations

from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import QApplication, QTableView

from gui.table_hover import PASTEL_BLUE_HOVER, enable_fast_cell_hover


def main() -> None:
    app = QApplication.instance() or QApplication([])
    table = QTableView()
    model = QStandardItemModel(3, 3, table)
    table.setModel(model)
    table.resize(420, 180)
    table.show()
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

    tracker.clear()
    assert not delegate.hovered_index.isValid()
    table.close()
    app.processEvents()


if __name__ == "__main__":
    main()
