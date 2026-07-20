from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .compact_filter_manager import CompactFilterManagerWidget


class ErgonomicFilterManagerWidget(CompactFilterManagerWidget):
    """Ergonomic presentation layer for the global filter editor.

    Frequently used controls stay visible. Global options, preset metadata,
    advanced tree actions, diagnostic JSON and the preset tester are collapsed
    until explicitly requested.
    """

    def _build_ui(self) -> None:
        super()._build_ui()
        self._configure_root_layout()
        self._configure_splitter()
        self._collapse_global_settings()
        self._simplify_preset_panel()
        self._collapse_tree_tools()
        self._move_transaction_controls_to_footer()

    def _configure_root_layout(self) -> None:
        root = self.layout()
        if root is None:
            return
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)

    def _configure_splitter(self) -> None:
        splitter = self.findChild(QSplitter)
        if splitter is None or splitter.count() < 3:
            return

        self.main_filter_splitter = splitter
        splitter.setObjectName("filterMainSplitter")
        splitter.setHandleWidth(6)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.widget(0).setMinimumWidth(285)
        splitter.widget(1).setMinimumWidth(430)
        splitter.widget(2).setMinimumWidth(350)
        splitter.setSizes([315, 690, 405])

        self.table.setAlternatingRowColors(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)

    def _collapse_global_settings(self) -> None:
        root = self.layout()
        bar = self.findChild(QWidget, "filterCombinationBar")
        if root is None or bar is None:
            return

        root.removeWidget(bar)
        box = QGroupBox(self)
        box.setObjectName("filterGlobalSettingsBox")
        box.setCheckable(True)
        box.setChecked(False)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 4, 8, 6)
        layout.setSpacing(0)
        bar.setParent(box)
        layout.addWidget(bar)

        self.global_settings_box = box
        self.global_settings_content = bar
        box.toggled.connect(bar.setVisible)
        self.combination_combo.currentIndexChanged.connect(
            self._update_global_settings_title
        )
        bar.setVisible(False)
        self._update_global_settings_title()
        root.insertWidget(1, box)

    def _update_global_settings_title(self, *_args: object) -> None:
        box = getattr(self, "global_settings_box", None)
        if box is None:
            return
        mode = str(self.combination_combo.currentData() or "and").upper()
        box.setTitle(f"Ustawienia globalne — presety Include: {mode}")

    def _simplify_preset_panel(self) -> None:
        self.table.setColumnHidden(2, True)
        self.table.setToolTip(
            "Kliknij nazwę, aby ją zmienić. Pole wyboru aktywuje preset dopiero po "
            "kliknięciu „Zastosuj zmiany”."
        )

        preset_box = self.name_edit.parentWidget()
        while preset_box is not None and not isinstance(preset_box, QGroupBox):
            preset_box = preset_box.parentWidget()
        if not isinstance(preset_box, QGroupBox):
            return

        self.preset_settings_box = preset_box
        preset_box.setObjectName("filterPresetSettingsBox")
        preset_box.setTitle("Wybrany preset")
        form = preset_box.layout()
        if not isinstance(form, QFormLayout):
            return

        toggle = QPushButton("Pokaż opis i skrót", preset_box)
        toggle.setObjectName("togglePresetAdvancedSettings")
        toggle.setCheckable(True)
        toggle.setToolTip(
            "Opis i skrót klawiaturowy są używane rzadziej niż nazwa, tryb i aktywność."
        )
        toggle.toggled.connect(self._toggle_preset_advanced_rows)
        form.addRow("", toggle)
        self.preset_advanced_toggle = toggle
        self._toggle_preset_advanced_rows(False)

    def _toggle_preset_advanced_rows(self, expanded: bool) -> None:
        self._set_form_row_visible(self.description_edit, expanded)
        self._set_form_row_visible(self.shortcut_edit, expanded)
        toggle = getattr(self, "preset_advanced_toggle", None)
        if toggle is not None:
            toggle.setText("Ukryj opis i skrót" if expanded else "Pokaż opis i skrót")

    def _collapse_tree_tools(self) -> None:
        splitter = getattr(self, "main_filter_splitter", None)
        if splitter is None or splitter.count() < 2:
            return
        panel = splitter.widget(1)
        panel_layout = panel.layout()
        if not isinstance(panel_layout, QVBoxLayout):
            return

        box = QGroupBox("Narzędzia drzewa — opcjonalne", panel)
        box.setObjectName("filterTreeToolsBox")
        box.setCheckable(True)
        box.setChecked(False)
        outer = QVBoxLayout(box)
        outer.setContentsMargins(8, 4, 8, 6)
        outer.setSpacing(6)

        content = QWidget(box)
        content.setObjectName("filterTreeToolsContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)

        actions = QWidget(content)
        action_layout = QHBoxLayout(actions)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(6)
        for text in ("+ NOT", "Duplikuj element", "↑", "↓", "Waliduj"):
            button = self._find_button(text)
            if button is not None:
                button.setParent(actions)
                action_layout.addWidget(button)
        action_layout.addStretch(1)
        content_layout.addWidget(actions)

        if self.json_box is not None:
            panel_layout.removeWidget(self.json_box)
            self.json_box.setParent(content)
            self.json_box.setTitle("Dane diagnostyczne JSON")
            content_layout.addWidget(self.json_box)

        outer.addWidget(content)
        content.setVisible(False)
        box.toggled.connect(content.setVisible)
        panel_layout.addWidget(box)

        self.tree_tools_box = box
        self.tree_tools_content = content

    def _move_transaction_controls_to_footer(self) -> None:
        root = self.layout()
        bar = self.findChild(QWidget, "filterTransactionBar")
        if root is None or bar is None:
            return

        parent = bar.parentWidget()
        parent_layout = parent.layout() if parent is not None else None
        if parent_layout is not None:
            parent_layout.removeWidget(bar)

        footer = QWidget(self)
        footer.setObjectName("filterTransactionFooter")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(8)

        self.save_state_label.setParent(footer)
        self.save_state_label.setObjectName("filterEditState")
        layout.addWidget(self.save_state_label)

        hint = QLabel(
            "Zmiany są robocze i nie wpływają na Live ani zapisane sesje przed zastosowaniem.",
            footer,
        )
        hint.setObjectName("filterTransactionHint")
        hint.setWordWrap(False)
        layout.addWidget(hint)
        layout.addStretch(1)

        bar.setParent(footer)
        layout.addWidget(bar)
        self.discard_button.setMinimumWidth(125)
        self.apply_button.setMinimumWidth(150)

        root.addWidget(footer)
        self.transaction_footer = footer

    def _set_form_row_visible(self, widget: QWidget, visible: bool) -> None:
        widget.setVisible(visible)
        parent = widget.parentWidget()
        form = parent.layout() if parent is not None else None
        label_for_field = getattr(form, "labelForField", None)
        if callable(label_for_field):
            label = label_for_field(widget)
            if label is not None:
                label.setVisible(visible)

    def _find_button(self, text: str) -> QPushButton | None:
        return next(
            (button for button in self.findChildren(QPushButton) if button.text() == text),
            None,
        )
