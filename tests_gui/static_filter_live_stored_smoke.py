from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from app.enhanced_stored_session_controller import EnhancedStoredSessionController
from app.filters import FilterMode, FilterPreset, ProjectFilterRepository
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter
from gui.final_streaming_filter_integration import FinalStreamingLiveFilterIntegration
from gui.live_capture import LiveCaptureWidget


def _preset() -> FilterPreset:
    preset = FilterPreset.create("Static Live/stored")
    preset.enabled = True
    preset.mode = FilterMode.INCLUDE
    preset.scope = ["live", "stored_session"]
    preset.root = {
        "type": "group",
        "operator": "and",
        "children": [
            {
                "type": "condition",
                "field": "can_id",
                "operator": "can_id_pattern",
                "values": ["0x18DA??00"],
            },
            {
                "type": "condition",
                "field": "payload",
                "operator": "payload_prefix",
                "values": ["62 F1 ??"],
            },
            {
                "type": "condition",
                "field": "channel",
                "operator": "eq",
                "values": ["1"],
            },
        ],
    }
    return preset


def _frames() -> tuple[CanFrame, ...]:
    return (
        CanFrame(
            sequence=1,
            timestamp_ns=1_000,
            arbitration_id=0x18DAF900,
            data=bytes.fromhex("62 F1 90"),
            channel=1,
            is_extended_id=True,
        ),
        CanFrame(
            sequence=2,
            timestamp_ns=2_000,
            arbitration_id=0x18DAF900,
            data=bytes.fromhex("7F 22 31"),
            channel=1,
            is_extended_id=True,
        ),
        CanFrame(
            sequence=3,
            timestamp_ns=3_000,
            arbitration_id=0x18DAAA00,
            data=bytes.fromhex("62 F1 AA 01"),
            channel=1,
            is_extended_id=True,
        ),
    )


def _write_session(path: Path, frames: tuple[CanFrame, ...]) -> None:
    session = CaptureSession(name="Static smoke", source="test")
    with SessionStreamWriter(session, path, flush_every=1, index_stride=2) as writer:
        for frame in frames:
            writer.append(frame)


def main() -> None:
    app = QApplication.instance() or QApplication([])

    with TemporaryDirectory() as temporary:
        project = CrtProject.create(f"{temporary}/project", name="Static filters")
        ProjectFilterRepository(project.database_path).save_presets([_preset()])
        frames = _frames()

        widget = LiveCaptureWidget(
            project,
            filter_integration_factory=FinalStreamingLiveFilterIntegration,
        )
        widget.frame_model.append_frames(frames)
        widget.apply_live_filters.setChecked(True)

        deadline = monotonic() + 10.0
        while not widget.live_filter_proxy.filter_ready and monotonic() < deadline:
            app.processEvents()
            QThreadPool.globalInstance().waitForDone(5)
            sleep(0.001)
        app.processEvents()

        assert widget.live_filter_proxy.filter_ready
        assert widget.frame_table.model() is widget.live_filter_proxy
        assert widget.live_filter_proxy.rowCount() == 2
        assert tuple(
            widget.live_filter_proxy.frame_at(index).sequence
            for index in range(widget.live_filter_proxy.rowCount())
        ) == (1, 3)
        widget.close()

        session_path = project.root / "sessions" / "static-smoke.crt.jsonl"
        session_path.parent.mkdir(parents=True, exist_ok=True)
        _write_session(session_path, frames)
        original_bytes = session_path.read_bytes()

        controller = EnhancedStoredSessionController(session_path, page_size=20)
        controller.start()
        controller.set_filters_enabled(True)
        deadline = monotonic() + 10.0
        state = controller.state
        while state.loading and monotonic() < deadline:
            sleep(0.005)
            state = controller.poll() or controller.state

        assert not state.loading
        assert not state.error
        assert state.page is not None
        assert tuple(frame.sequence for frame in state.page.frames) == (1, 3)
        assert state.page.visible_frames == 2
        assert session_path.read_bytes() == original_bytes
        controller.shutdown()

    app.processEvents()


if __name__ == "__main__":
    main()
