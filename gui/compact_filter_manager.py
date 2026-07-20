from __future__ import annotations

from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QWidget

from app.filter_preferences import FilterCombinationMode

from .enhanced_filter_manager import EnhancedFilterManagerWidget


class CompactFilterManagerWidget(EnhancedFilterManagerWidget):
    """Filter editor with the Include-combination option rendered as one compact row."""

    def _build_ui(self) -> None:
        super()._build_ui()

        root = self.layout()
        if root is None:
            return

        old_box = self.combination_combo.parentWidget()
        while old_box is not None and not isinstance(old_box, QGroupBox):
            old_box = old_box.parentWidget()

        details = (
            "AND: rekord musi pasować do wszystkich aktywnych presetów Include.\n"
            "OR: rekord może pasować do dowolnego aktywnego presetu Include.\n"
            "Exclude nadal ukrywa po dopasowaniu dowolnego presetu, a Highlight nie zmienia widoczności."
        )

        bar = QWidget(self)
        bar.setObjectName("filterCombinationBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        label = QLabel("Łączenie presetów Include:", bar)
        label.setObjectName("filterCombinationLabel")
        label.setToolTip(details)
        layout.addWidget(label)

        self.combination_combo.setParent(bar)
        self.combination_combo.setToolTip(details)
        self.combination_combo.setMaximumWidth(260)
        and_index = self.combination_combo.findData(FilterCombinationMode.AND.value)
        or_index = self.combination_combo.findData(FilterCombinationMode.OR.value)
        if and_index >= 0:
            self.combination_combo.setItemText(and_index, "AND — wszystkie")
        if or_index >= 0:
            self.combination_combo.setItemText(or_index, "OR — dowolny")
        layout.addWidget(self.combination_combo)
        layout.addStretch(1)

        if old_box is not None:
            root.removeWidget(old_box)
            old_box.hide()
            old_box.deleteLater()

        root.insertWidget(1, bar)
