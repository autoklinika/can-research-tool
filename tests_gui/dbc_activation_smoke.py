from __future__ import annotations

import os
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.dbc import DbcFileRecord
import gui.dbc_manager as dbc_manager


app = QApplication.instance() or QApplication([])
records = [
    DbcFileRecord(
        id="dbc-1",
        name="engine",
        relative_path="decoders/dbc/engine.dbc",
        enabled=False,
        message_count=12,
        sha256="a" * 64,
        added_at_utc="2026-07-16T00:00:00+00:00",
    )
]


def fake_list_project_dbc(project):
    return list(records)


def fake_set_project_dbc_enabled(project, dbc_id: str, enabled: bool) -> None:
    assert dbc_id == "dbc-1"
    records[0] = replace(records[0], enabled=bool(enabled))


dbc_manager.list_project_dbc = fake_list_project_dbc
dbc_manager.set_project_dbc_enabled = fake_set_project_dbc_enabled

model = dbc_manager.DbcTableModel(object())
index = model.index(0, 0)

assert model.data(index, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked
assert model.flags(index) & Qt.ItemFlag.ItemIsUserCheckable

# PySide may deliver either a Qt.CheckState enum or its integer value.
assert model.setData(index, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
assert records[0].enabled is True
assert model.data(index, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked

assert model.setData(index, Qt.CheckState.Unchecked.value, Qt.ItemDataRole.CheckStateRole)
assert records[0].enabled is False
assert model.data(index, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked

widget = dbc_manager.DbcManagerWidget(object())
widget.table.selectRow(0)
widget._toggle_selected()
app.processEvents()
assert records[0].enabled is True
assert widget.model.active_count == 1
assert widget.summary.text() == "Aktywne: 1 / 1"

widget.close()
print("DBC activation GUI smoke: OK")
