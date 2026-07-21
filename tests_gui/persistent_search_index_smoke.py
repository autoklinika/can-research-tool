from __future__ import annotations

import time
from tempfile import TemporaryDirectory

from PySide6.QtWidgets import QApplication, QTableView

from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.query_engine import QueryEngine
from app.search_engine import SearchQuery
from app.session_stream import SessionStreamWriter
from gui.frame_model import FrameTableModel
from gui.persistent_search_index import PersistentSessionSearchIndex
from gui.search_index_registry import SearchIndexRegistry


def main() -> None:
    app = QApplication.instance() or QApplication([])

    with TemporaryDirectory() as temporary:
        project = CrtProject.create(f"{temporary}/project", name="Persistent smoke")
        path = project.imported_sessions_dir / "sample.crt.jsonl"
        frames = [
            CanFrame(1, 1_000_000, 0x123, b"\x27\x07"),
            CanFrame(2, 2_000_000, 0x18DAF900, b"\x67\x07", is_extended_id=True),
        ]
        with SessionStreamWriter(CaptureSession("sample", "test"), path) as writer:
            for frame in frames:
                writer.append(frame)
        project.register_session(path, name="sample", source="test", status="ready")
        project.finalize_session(
            path,
            frame_count=len(frames),
            marker_count=0,
            duration_s=0.0,
        )

        search_database = project.root / ".crt" / "indexes" / "search-v1.sqlite"
        registry = SearchIndexRegistry()
        assert not search_database.exists()

        model = FrameTableModel(capacity=len(frames))
        model.replace_frames(frames)
        table = QTableView()
        table.setModel(model)

        index = registry.index_for_table(table, project=project, session_path=path)
        assert isinstance(index, PersistentSessionSearchIndex)
        assert search_database.is_file()
        deadline = time.monotonic() + 5.0
        while not index.is_ready and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        assert index.is_ready

        result = QueryEngine().search(index.snapshot(), SearchQuery("18DAF900"))
        assert [hit.row for hit in result.hits] == [1]
        registry.close()

        reopened_project = CrtProject.open(project.root)
        reopened_registry = SearchIndexRegistry()
        reused = reopened_registry.index_for_table(
            table,
            project=reopened_project,
            session_path=path,
        )
        assert isinstance(reused, PersistentSessionSearchIndex)
        assert reused.is_ready
        assert reused.progress == (len(frames), len(frames))
        reopened_registry.close()
        table.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    main()
