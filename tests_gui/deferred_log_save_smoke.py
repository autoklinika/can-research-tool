from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QCheckBox, QLabel

from app.capture_service import CapturePaths, CaptureState, CaptureStatus
from app.project import CrtProject
from gui.application_container import ApplicationContainer


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("Autoklinika-tests")
    app.setApplicationName("CRT-deferred-log-save")

    with TemporaryDirectory() as temporary:
        project = CrtProject.create(Path(temporary) / "project", name="Deferred save")
        window = ApplicationContainer().create_main_window()
        window._set_project(project)
        window._open_live_capture()
        app.processEvents()

        live = window.navigator.widget("live-capture")
        assert live is not None
        integration = live._live_save_integration

        assert live.findChild(QCheckBox, "armSessionSaveButton") is None
        assert live.session_name.isHidden()
        assert not any(
            label.isVisible() and label.text().strip() == "Nazwa sesji:"
            for label in live.findChildren(QLabel)
        )

        file_menu = next(
            action.menu()
            for action in window.menuBar().actions()
            if action.text().replace("&", "") == "Plik"
        )
        assert file_menu is not None
        assert window.save_log_action in file_menu.actions()
        assert not window.save_log_action.isEnabled()

        temp_dir = project.root / ".crt" / "temp" / "live"
        temp_dir.mkdir(parents=True, exist_ok=True)
        paths = CapturePaths(
            session=temp_dir / "live_temp_technical.crt.jsonl",
            raw_frames_csv=temp_dir / "live_temp_technical.frames.csv",
            logical_messages_csv=temp_dir / "live_temp_technical.messages.csv",
            markers=temp_dir / "live_temp_technical.markers.jsonl",
        )
        paths.session.write_text('{"record":"session"}\n', encoding="utf-8")
        paths.raw_frames_csv.write_text("timestamp_ns\n", encoding="utf-8")
        paths.markers.write_text("", encoding="utf-8")

        status = CaptureStatus(
            state=CaptureState.STOPPED,
            elapsed_s=1.25,
            frame_count=42,
            logical_message_count=0,
            incomplete_message_count=0,
            marker_count=2,
            unique_can_ids=3,
            adapter_name="Virtual",
            error="",
            paths=paths,
            persist_to_disk=True,
            live_capacity=20_000,
            live_retained=42,
            live_dropped_from_view=0,
            live_message_capacity=1,
            live_messages_retained=0,
            live_messages_dropped_from_view=0,
            last_marker=None,
        )
        integration._pending_paths = paths
        integration._pending_status = status
        integration._pending_name = "live_temp_technical"
        integration._transient_finalized = True
        integration._request_log_name = lambda: "EGR próba 01"
        live._analysis_session_path = paths.session

        window._sync_save_log_action()
        assert window.save_log_action.isEnabled()
        window._save_pending_live_log()
        app.processEvents()

        saved = project.live_sessions_dir / "EGR_pr_ba_01.crt.jsonl"
        assert saved.is_file()
        assert not paths.session.exists()
        record = project.session_by_path(saved)
        assert record is not None
        assert record.name == "EGR próba 01"
        assert record.status == "ready"
        assert record.frame_count == 42
        assert record.marker_count == 2
        assert not integration.has_unsaved_log
        assert not window.save_log_action.isEnabled()

        window.close()
        window.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    main()
