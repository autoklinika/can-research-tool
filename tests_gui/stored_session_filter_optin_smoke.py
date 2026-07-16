from __future__ import annotations

from tempfile import TemporaryDirectory

from PySide6.QtWidgets import QApplication

from app.filters import FilterMode, FilterPreset, ProjectFilterRepository
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter
from gui.session_filter_integration import install_session_filter_integration
from gui.session_view import SessionViewWidget


def main() -> None:
    app = QApplication.instance() or QApplication([])
    install_session_filter_integration()

    with TemporaryDirectory() as temporary:
        project = CrtProject.create(f"{temporary}/project", name="Filter opt-in")
        preset = FilterPreset.create("Only 0x100")
        preset.enabled = True
        preset.mode = FilterMode.INCLUDE
        preset.root = {
            "type": "group",
            "operator": "and",
            "children": [
                {
                    "type": "condition",
                    "field": "can_id",
                    "operator": "eq",
                    "values": ["0x100"],
                }
            ],
        }
        ProjectFilterRepository(project.database_path).save_presets([preset])

        session_path = project.live_sessions_dir / "optin.crt.jsonl"
        with SessionStreamWriter(CaptureSession(name="optin", source="test"), session_path) as writer:
            writer.append(CanFrame(sequence=0, timestamp_ns=0, arbitration_id=0x100, data=b"\x01"))
            writer.append(CanFrame(sequence=1, timestamp_ns=1_000_000, arbitration_id=0x200, data=b"\x02"))

        widget = SessionViewWidget(session_path)
        assert widget.stored_apply_filters.isChecked() is False
        assert widget._stored_available_filter_set.active_count == 1
        assert widget._stored_filter_set.active_count == 0

        widget.stored_apply_filters.setChecked(True)
        assert widget._stored_filter_set.active_count == 1

        widget.stored_apply_filters.setChecked(False)
        assert widget._stored_filter_set.active_count == 0
        widget.close()

    app.processEvents()


if __name__ == "__main__":
    main()
