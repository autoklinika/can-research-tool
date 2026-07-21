from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QWidget,
)

from app.models import CanFrame

from .final_streaming_filter_integration import FinalStreamingLiveFilterIntegration
from .grouped_frame_model import GroupedFrameTableModel


class GroupedFinalStreamingLiveFilterIntegration(
    FinalStreamingLiveFilterIntegration
):
    """Add List/Grouped-by-ID presentation without changing capture semantics."""

    def __init__(self, widget) -> None:
        self._grouped_view_enabled = False
        self._frame_display_filtered = False
        self.raw_grouped_model = GroupedFrameTableModel(widget)
        self.filtered_grouped_model = GroupedFrameTableModel(widget)
        super().__init__(widget)

        widget.grouped_frame_model = self.raw_grouped_model
        widget.live_grouped_filter_model = self.filtered_grouped_model

        widget.frame_model.modelReset.connect(self._rebuild_raw_grouped_model)
        widget.frame_model.rowsInserted.connect(self._raw_rows_inserted)
        self.proxy.modelReset.connect(self._rebuild_filtered_grouped_model)
        self.proxy.rowsInserted.connect(self._filtered_rows_inserted)

        self._rebuild_raw_grouped_model()
        self._rebuild_filtered_grouped_model()
        self._install_view_controls()
        self._set_frame_display_model(
            self.proxy.filter_enabled and self.proxy.filter_ready
        )
        self._update_live_counts()

    def selected_frame(self) -> CanFrame | None:
        rows = self.widget.frame_table.selectionModel().selectedRows()
        if not rows:
            return None
        model = self.widget.frame_table.model()
        frame_at = getattr(model, "frame_at", None)
        if callable(frame_at):
            return frame_at(rows[0].row())
        return super().selected_frame()

    def _install_view_controls(self) -> None:
        raw_page = self.widget.data_tabs.widget(self.widget.raw_tab_index)
        raw_layout = raw_page.layout()

        controls = QWidget(raw_page)
        controls.setObjectName("rawFrameViewControls")
        row = QHBoxLayout(controls)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(QLabel("Widok:"))

        list_button = QRadioButton("Lista")
        list_button.setObjectName("rawFrameListView")
        list_button.setToolTip(
            "Każda odebrana ramka CAN jest wyświetlana jako osobny wiersz."
        )
        grouped_button = QRadioButton("Grupuj po ID")
        grouped_button.setObjectName("rawFrameGroupedView")
        grouped_button.setToolTip(
            "Jeden stabilny wiersz dla każdego kanału, formatu STD/EXT i CAN ID. "
            "Nowsza ramka aktualizuje czas, sekwencję, DLC, dane oraz flagi."
        )

        button_group = QButtonGroup(controls)
        button_group.setExclusive(True)
        button_group.addButton(list_button)
        button_group.addButton(grouped_button)
        list_button.setChecked(True)
        grouped_button.toggled.connect(self._set_grouped_view_enabled)

        row.addWidget(list_button)
        row.addWidget(grouped_button)
        row.addStretch(1)
        raw_layout.insertWidget(0, controls)

        self.widget.raw_frame_view_controls = controls
        self.widget.raw_frame_view_group = button_group
        self.widget.raw_frame_list_view = list_button
        self.widget.raw_frame_grouped_view = grouped_button

    def _set_grouped_view_enabled(self, enabled: bool) -> None:
        self._grouped_view_enabled = bool(enabled)
        self._set_frame_display_model(self._frame_display_filtered)
        self._update_live_counts()

    def _set_frame_display_model(self, filtered: bool) -> None:
        self._frame_display_filtered = bool(filtered)
        if not self._grouped_view_enabled:
            super()._set_frame_display_model(filtered)
            return
        target = (
            self.filtered_grouped_model
            if self._frame_display_filtered
            else self.raw_grouped_model
        )
        self._bind_frame_table(target)

    def _bind_frame_table(self, model) -> None:
        table = self.widget.frame_table
        if table.model() is model:
            return
        table.setModel(model)
        table.selectionModel().selectionChanged.connect(self.widget._frame_selected)

    def _rebuild_raw_grouped_model(self) -> None:
        self.raw_grouped_model.replace_frames(
            self.widget.frame_model.snapshot_frames()
        )

    def _raw_rows_inserted(self, _parent, first: int, last: int) -> None:
        self.raw_grouped_model.append_frames(
            _frames_from_model(self.widget.frame_model, first, last)
        )

    def _rebuild_filtered_grouped_model(self) -> None:
        if not self.proxy.filter_enabled or not self.proxy.filter_ready:
            self.filtered_grouped_model.clear()
            return
        self.filtered_grouped_model.replace_frames(
            _frames_from_model(self.proxy, 0, self.proxy.rowCount() - 1)
        )

    def _filtered_rows_inserted(self, _parent, first: int, last: int) -> None:
        if not self.proxy.filter_enabled or not self.proxy.filter_ready:
            return
        self.filtered_grouped_model.append_frames(
            _frames_from_model(self.proxy, first, last)
        )

    def _update_live_counts(
        self,
        total_received: int | None = None,
        logical_total: int | None = None,
    ) -> None:
        super()._update_live_counts(total_received, logical_total)
        if not self._grouped_view_enabled:
            return

        model = (
            self.filtered_grouped_model
            if self._frame_display_filtered
            else self.raw_grouped_model
        )
        visible_groups = model.rowCount()
        retained = self.widget.frame_model.frame_count
        if total_received is None:
            try:
                total_received = int(self.widget._controller.status().frame_count)
            except Exception:
                total_received = retained
        suffix = " (przeliczanie filtrów)" if self.proxy.filter_scanning else ""
        self.widget.visible_label.setText(
            (
                f"Widoczne ID: {visible_groups:,} / bufor {retained:,}{suffix}"
            ).replace(",", " ")
        )
        self.widget.data_tabs.setTabText(
            self.widget.raw_tab_index,
            (
                f"Surowe ramki — grupy ID "
                f"({visible_groups:,}/{total_received:,})"
            ).replace(",", " "),
        )


def _frames_from_model(model, first: int, last: int) -> tuple[CanFrame, ...]:
    if first < 0 or last < first:
        return ()
    frames: list[CanFrame] = []
    frame_at = getattr(model, "frame_at", None)
    if not callable(frame_at):
        return ()
    for row in range(first, last + 1):
        frame = frame_at(row)
        if isinstance(frame, CanFrame):
            frames.append(frame)
    return tuple(frames)
