from __future__ import annotations

from gc import collect
from tempfile import TemporaryDirectory

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from app.filter_preferences import FilterCombinationMode, ProjectFilterPreferences
from app.filters import ProjectFilterRepository
from app.project import CrtProject
from app.static_filter_engine import StaticFilterField, StaticFilterOperator
from gui.ergonomic_filter_manager import ErgonomicFilterManagerWidget


def _combo_data(combo) -> tuple[str, ...]:
    return tuple(str(combo.itemData(index)) for index in range(combo.count()))


def main() -> None:
    app = QApplication.instance() or QApplication([])

    with TemporaryDirectory() as temporary:
        project = CrtProject.create(f"{temporary}/project", name="Static filter editor")
        repository = ProjectFilterRepository(project.database_path)
        preferences = ProjectFilterPreferences(project.database_path)
        manager = ErgonomicFilterManagerWidget(project)
        manager._add_preset()
        manager._select_tree_path((0,))
        app.processEvents()

        # Primary actions are fixed in a global footer, not buried in the preset column.
        transaction_bar = manager.findChild(QWidget, "filterTransactionBar")
        transaction_footer = manager.findChild(QWidget, "filterTransactionFooter")
        assert transaction_bar is not None
        assert transaction_footer is not None
        assert transaction_bar.parentWidget() is transaction_footer
        assert manager.save_state_label.parentWidget() is transaction_footer
        assert manager.apply_button.text() == "Zastosuj zmiany"
        assert manager.discard_button.text() == "Odrzuć zmiany"
        assert manager.has_pending_changes
        assert manager.apply_button.isEnabled()
        assert manager.discard_button.isEnabled()
        assert repository.list_presets() == []

        # Rare global options are collapsed but their current state remains in the title.
        combination_bar = manager.findChild(QWidget, "filterCombinationBar")
        assert combination_bar is not None
        assert manager.global_settings_box.isCheckable()
        assert not manager.global_settings_box.isChecked()
        assert manager.global_settings_content.isHidden()
        assert "AND" in manager.global_settings_box.title()
        manager.global_settings_box.setChecked(True)
        app.processEvents()
        assert not manager.global_settings_content.isHidden()
        assert manager.combination_combo.parentWidget() is combination_bar
        assert manager.combination_combo.maximumWidth() == 260
        assert manager.combination_combo.itemText(
            manager.combination_combo.findData(FilterCombinationMode.AND.value)
        ) == "AND — wszystkie"
        assert manager.combination_combo.itemText(
            manager.combination_combo.findData(FilterCombinationMode.OR.value)
        ) == "OR — dowolny"

        manager.combination_combo.setCurrentIndex(
            manager.combination_combo.findData(FilterCombinationMode.OR.value)
        )
        assert "OR" in manager.global_settings_box.title()
        manager._autosave()
        assert repository.list_presets() == []
        assert preferences.combination_mode() is FilterCombinationMode.AND

        # Preset list stays compact; description and shortcut are available on demand.
        assert manager.table.isColumnHidden(2)
        assert manager.description_edit.isHidden()
        assert manager.shortcut_edit.isHidden()
        assert manager.preset_advanced_toggle.text() == "Pokaż opis i skrót"
        manager.preset_advanced_toggle.setChecked(True)
        app.processEvents()
        assert not manager.description_edit.isHidden()
        assert not manager.shortcut_edit.isHidden()
        assert manager.preset_advanced_toggle.text() == "Ukryj opis i skrót"
        manager.preset_advanced_toggle.setChecked(False)

        # Advanced tree actions and diagnostic JSON stay out of the primary workflow.
        assert manager.tree_tools_box.isCheckable()
        assert not manager.tree_tools_box.isChecked()
        assert manager.tree_tools_content.isHidden()
        assert manager.json_box.parentWidget() is manager.tree_tools_content
        manager.tree_tools_box.setChecked(True)
        app.processEvents()
        assert not manager.tree_tools_content.isHidden()

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

        # Typing at the beginning must not rebuild the editor or move the cursor.
        manager.condition_values.setText("62 F1 ??")
        manager.condition_values.setCursorPosition(0)
        manager.condition_values.setFocus()
        QTest.keyClicks(manager.condition_values, "A0 ")
        app.processEvents()
        assert manager.condition_values.text() == "A0 62 F1 ??"
        assert manager.condition_values.cursorPosition() == 3

        manager.condition_values.setText("62 F1 ??")
        manager._condition_values_edited("62 F1 ??")
        assert not manager.compiler.validate(manager._current_preset())

        # The optional preset test stays collapsed until explicitly requested.
        assert manager.test_box.objectName() == "filterPresetTestBox"
        assert manager.test_box.title() == "Test presetu — opcjonalny"
        assert manager.test_box.isCheckable()
        assert not manager.test_box.isChecked()
        assert manager.test_context.isHidden()

        manager.test_box.setChecked(True)
        app.processEvents()
        assert not manager.test_context.isHidden()
        logical_label = manager.test_box.layout().labelForField(manager.test_logical_json)
        assert manager.test_logical_json.isHidden()
        assert logical_label is not None and logical_label.isHidden()

        manager.test_payload.setText("62 F1 90")
        manager.test_dlc.setValue(3)
        manager._test_current()
        assert manager.test_result.text() == "PASUJE"

        manager.test_context.setCurrentIndex(manager.test_context.findData("logical"))
        app.processEvents()
        assert not manager.test_logical_json.isHidden()
        assert logical_label is not None and not logical_label.isHidden()
        manager._test_current()
        assert manager.test_result.text().startswith("NIEDOSTĘPNE")

        manager.apply_button.click()
        app.processEvents()
        saved = repository.list_presets()
        assert len(saved) == 1
        assert preferences.combination_mode() is FilterCombinationMode.OR
        assert not manager.has_pending_changes
        assert not manager.apply_button.isEnabled()
        assert not manager.discard_button.isEnabled()

        persisted_name = saved[0].name
        manager.name_edit.setText("Robocza nazwa — nie zapisuj")
        manager._preset_editor_changed()
        assert manager.has_pending_changes
        assert repository.list_presets()[0].name == persisted_name

        manager.discard_button.click()
        app.processEvents()
        assert not manager.has_pending_changes
        assert manager._current_preset().name == persisted_name
        assert repository.list_presets()[0].name == persisted_name
        assert manager.combination_mode is FilterCombinationMode.OR

        manager.close()
        manager.deleteLater()
        app.processEvents()
        del manager
        collect()

    app.processEvents()


if __name__ == "__main__":
    main()
