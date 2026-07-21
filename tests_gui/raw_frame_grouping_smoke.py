from __future__ import annotations

from gc import collect
from tempfile import TemporaryDirectory

from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool, QTimer
from PySide6.QtWidgets import QApplication

from app.models import CanFrame
from app.project import CrtProject
from gui.grouped_frame_model import GroupedFrameTableModel
from gui.live_capture import LiveCaptureWidget
from gui.raw_frame_grouping import GroupedFinalStreamingLiveFilterIntegration


def _frame(
    sequence: int,
    can_id: int,
    value: int,
    *,
    channel: int = 0,
    extended: bool = False,
) -> CanFrame:
    return CanFrame(
        sequence=sequence,
        timestamp_ns=sequence * 1_000_000,
        arbitration_id=can_id,
        data=bytes((value,)),
        channel=channel,
        is_extended_id=extended,
    )


def _dispose_widget(app: QApplication, widget: LiveCaptureWidget) -> None:
    widget.shutdown()
    for timer in widget.findChildren(QTimer):
        timer.stop()
    QThreadPool.globalInstance().waitForDone(5_000)
    widget.close()
    app.processEvents()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def main() -> None:
    app = QApplication.instance() or QApplication([])

    model = GroupedFrameTableModel()
    frames = (
        _frame(1, 0x100, 0x01),
        _frame(2, 0x200, 0x02),
        _frame(3, 0x100, 0x03),
        _frame(4, 0x100, 0x04, channel=1),
        _frame(5, 0x100, 0x05, extended=True),
    )
    model.append_frames(frames)
    assert model.rowCount() == 4
    assert model.frame_at(0).sequence == 3
    assert model.frame_at(0).data == b"\x03"
    assert model.frame_at(2).channel == 1
    assert model.frame_at(3).is_extended_id is True

    model.append_frames((_frame(6, 0x100, 0x06),))
    assert model.rowCount() == 4
    assert model.frame_at(0).sequence == 6

    with TemporaryDirectory() as temporary:
        project = CrtProject.create(f"{temporary}/project", name="Raw grouping")
        widget = LiveCaptureWidget(
            project,
            filter_integration_factory=GroupedFinalStreamingLiveFilterIntegration,
        )
        integration = widget._live_filter_integration

        assert widget.raw_frame_list_view.isChecked()
        assert widget.frame_table.model() is widget.frame_model

        widget.frame_model.append_frames(frames)
        app.processEvents()
        assert widget.grouped_frame_model.rowCount() == 4

        widget.raw_frame_grouped_view.setChecked(True)
        app.processEvents()
        assert widget.frame_table.model() is widget.grouped_frame_model
        assert widget.frame_table.model().rowCount() == 4
        assert widget.frame_table.model().frame_at(0).sequence == 3

        proxy = widget.live_filter_proxy
        proxy.beginResetModel()
        proxy.filter_enabled = True
        proxy.filter_ready = True
        proxy.filter_scanning = False
        proxy._frames = [frames[0], frames[2]]
        proxy.endResetModel()
        integration._set_frame_display_model(True)
        app.processEvents()

        assert widget.frame_table.model() is widget.live_grouped_filter_model
        assert widget.frame_table.model().rowCount() == 1
        assert widget.frame_table.model().frame_at(0).sequence == 3

        widget.frame_table.selectRow(0)
        assert integration.selected_frame().sequence == 3

        widget.raw_frame_list_view.setChecked(True)
        app.processEvents()
        assert widget.frame_table.model() is proxy
        assert widget.frame_table.model().rowCount() == 2

        widget.raw_frame_grouped_view.setChecked(True)
        integration._set_frame_display_model(False)
        app.processEvents()
        assert widget.frame_table.model() is widget.grouped_frame_model
        assert widget.frame_table.model().rowCount() == 4

        _dispose_widget(app, widget)
        del widget
        del project
        collect()

    model.deleteLater()
    app.processEvents()


if __name__ == "__main__":
    main()
