from __future__ import annotations

from PySide6.QtCore import (
    QEvent,
    QModelIndex,
    QObject,
    QPoint,
    QPersistentModelIndex,
    Qt,
    QTimer,
)
from PySide6.QtGui import QBrush, QColor, QCursor, QHoverEvent, QMouseEvent, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTableView


PASTEL_BLUE_HOVER = QColor("#DCEEFF")


class FastCellHoverDelegate(QStyledItemDelegate):
    """Paint one hovered table cell without invalidating the whole viewport."""

    def __init__(
        self,
        table: QTableView,
        color: QColor | str = PASTEL_BLUE_HOVER,
    ) -> None:
        super().__init__(table)
        self._table = table
        self._hovered = QPersistentModelIndex()
        self._hover_color = QColor(color)
        self._hover_brush = QBrush(self._hover_color)

    @property
    def hovered_index(self) -> QModelIndex:
        return QModelIndex(self._hovered)

    @property
    def hover_color(self) -> QColor:
        return QColor(self._hover_color)

    def set_hovered_index(self, index: QModelIndex) -> None:
        if index.isValid() and index.model() is not self._table.model():
            index = QModelIndex()
        old_index = QModelIndex(self._hovered)
        if old_index == index:
            return
        self._hovered = (
            QPersistentModelIndex(index) if index.isValid() else QPersistentModelIndex()
        )
        self._update_cell(old_index)
        self._update_cell(index)

    def clear_hover(self) -> None:
        self.set_hovered_index(QModelIndex())

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        adjusted = QStyleOptionViewItem(option)
        adjusted.state &= ~QStyle.StateFlag.State_MouseOver
        if (
            self._hovered.isValid()
            and QModelIndex(self._hovered) == index
            and not adjusted.state & QStyle.StateFlag.State_Selected
        ):
            adjusted.features &= ~QStyleOptionViewItem.ViewItemFeature.Alternate
            adjusted.backgroundBrush = self._hover_brush
        super().paint(painter, adjusted, index)

    def _update_cell(self, index: QModelIndex) -> None:
        if not index.isValid() or index.model() is not self._table.model():
            return
        rect = self._table.visualRect(index)
        if rect.isValid():
            self._table.viewport().update(rect)


class FastCellHoverTracker(QObject):
    """Track the cursor synchronously and repaint only the old and new cell."""

    def __init__(self, table: QTableView, delegate: FastCellHoverDelegate) -> None:
        super().__init__(table)
        self._table = table
        self._delegate = delegate
        viewport = table.viewport()
        table.setMouseTracking(True)
        viewport.setMouseTracking(True)
        viewport.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        viewport.installEventFilter(self)
        table.horizontalScrollBar().valueChanged.connect(self._schedule_cursor_sync)
        table.verticalScrollBar().valueChanged.connect(self._schedule_cursor_sync)

    def update_from_position(self, position: QPoint) -> None:
        viewport = self._table.viewport()
        index = (
            self._table.indexAt(position)
            if viewport.rect().contains(position)
            else QModelIndex()
        )
        self._delegate.set_hovered_index(index)

    def clear(self) -> None:
        self._delegate.clear_hover()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self._table.viewport():
            event_type = event.type()
            if event_type == QEvent.Type.MouseMove and isinstance(event, QMouseEvent):
                self.update_from_position(event.position().toPoint())
            elif event_type == QEvent.Type.HoverMove and isinstance(event, QHoverEvent):
                self.update_from_position(event.position().toPoint())
            elif event_type == QEvent.Type.Leave:
                self.clear()
            elif event_type in {
                QEvent.Type.Wheel,
                QEvent.Type.Resize,
                QEvent.Type.Show,
            }:
                self._schedule_cursor_sync()
        return False

    def _schedule_cursor_sync(self, *_args: object) -> None:
        QTimer.singleShot(0, self._sync_from_cursor)

    def _sync_from_cursor(self) -> None:
        viewport = self._table.viewport()
        self.update_from_position(viewport.mapFromGlobal(QCursor.pos()))


def enable_fast_cell_hover(
    table: QTableView,
    *,
    color: QColor | str = PASTEL_BLUE_HOVER,
) -> FastCellHoverDelegate:
    """Enable low-overhead cell hover tracking and retain Qt object ownership."""

    delegate = FastCellHoverDelegate(table, color)
    tracker = FastCellHoverTracker(table, delegate)
    table.setItemDelegate(delegate)
    table._crt_hover_delegate = delegate  # type: ignore[attr-defined]
    table._crt_hover_tracker = tracker  # type: ignore[attr-defined]
    return delegate
