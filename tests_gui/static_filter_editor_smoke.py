from __future__ import annotations

from tempfile import TemporaryDirectory

from PySide6.QtWidgets import QApplication, QWidget

from app.filter_preferences import FilterCombinationMode
from app.project import CrtProject
from app.static_filter_engine import StaticFilterField, StaticFilterOperator
from gui.compact_filter_manager import CompactFilterManagerWidget


def _combo_data(combo) -> tuple[str, ...]:
    return tuple(str(combo.itemData(index)) for index in range(combo.count()))


def main() -> None:
    app = QApplication.instance() or QApplication([])

    with TemporaryDirectory() as temporary:
        project = CrtProject.create(f"{temporary}/project", name="Static filter editor")
        manager = CompactFilterManagerWidget(project)
        manager._add_preset()
        manager._select_tree_path((0,))
        app.processEvents()

        combination_bar = manager.findChild(QWidget, "filterCombinationBar")
        assert combination_bar is not None
        assert manager.combination_combo.parentWidget() is combination_bar
        assert manager.combination_combo.maximumWidth() == 260
        assert manager.combination_combo.itemText(
            manager.combination_combo.findData(FilterCombinationMode.AND.value)
        ) == "AND — wszystkie"
        assert manager.combination_combo.itemText(
            manager.combination_combo.findData(FilterCombinationMode.OR.value)
        ) == "OR — dowolny"

        for field_name in (
            StaticFilterField.CHANNEL.value,
            StaticFilterField.RTR.value,
            StaticFilterField.ERROR_FRAME.value,
            StaticFilterField.PAYLOAD.value,
        ):
            assert manager.condition_field.findData(field_name) >= 0

        can_id_index = manager.condition_field.findData("can_id")
        manager.condition_field.setCurrentIndex(can_id_index)
        app.processEvents()
        assert (
            manager.condition_operator.findData(
                StaticFilterOperator.CAN_ID_PATTERN.value
            )
            >= 0
        )

        payload_index = manager.condition_field.findData(StaticFilterField.PAYLOAD.value)
        manager.condition_field.setCurrentIndex(payload_index)
        app.processEvents()
        assert _combo_data(manager.condition_operator) == (
            StaticFilterOperator.PAYLOAD_EXACT.value,
            StaticFilterOperator.PAYLOAD_PREFIX.value,
            StaticFilterOperator.PAYLOAD_CONTAINS.value,
        )
        assert (
            manager.condition_operator.currentData()
            == StaticFilterOperator.PAYLOAD_EXACT.value
        )

        manager.condition_values.setText("62 F1 ??")
        manager._condition_property_changed()
        assert not manager.compiler.validate(manager._current_preset())

        manager.test_payload.setText("62 F1 90")
        manager.test_dlc.setValue(3)
        manager._test_current()
        assert manager.test_result.text() == "MATCH"

        manager.test_context.setCurrentIndex(manager.test_context.findData("logical"))
        manager._test_current()
        assert manager.test_result.text().startswith("UNAVAILABLE")

        manager.close()

    app.processEvents()


if __name__ == "__main__":
    main()
