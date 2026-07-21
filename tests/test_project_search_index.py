from __future__ import annotations

import os
from threading import Event

from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.project_search_index import ProjectSearchIndex
from app.query_engine import QueryEngine
from app.search_engine import SearchQuery
from app.session_management import remove_session
from app.session_stream import SessionStreamWriter


def _create_session(project: CrtProject, name: str, frames: list[CanFrame]):
    path = project.imported_sessions_dir / f"{name}.crt.jsonl"
    session = CaptureSession(name=name, source="test")
    with SessionStreamWriter(session, path) as writer:
        for frame in frames:
            writer.append(frame)
    project.register_session(path, name=name, source="test", status="ready")
    project.finalize_session(
        path,
        frame_count=len(frames),
        marker_count=0,
        duration_s=0.0,
    )
    record = project.session_by_path(path)
    assert record is not None
    return path, record


def test_persistent_index_survives_project_reopen_and_executes_sql_query(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Persistent search")
    path, record = _create_session(
        project,
        "sample",
        [
            CanFrame(1, 1_000_000, 0x123, b"\x27\x07"),
            CanFrame(2, 2_000_000, 0x18DAF900, b"\x67\x07", is_extended_id=True),
            CanFrame(3, 3_000_000, 0x18DAF900, b"\x7F\x27\x35", is_extended_id=True),
        ],
    )

    repository = ProjectSearchIndex(project)
    fingerprint = repository.rebuild_session(project, record)
    assert repository.is_current(fingerprint)
    assert repository.path.is_file()

    result = QueryEngine().search(
        repository.source(fingerprint.source_id),
        SearchQuery("18DAF900", fields=frozenset({"CAN ID"})),
    )
    assert [hit.row for hit in result.hits] == [1, 2]
    assert result.scanned_documents == 2

    # Simulate a Windows utility touching file metadata between CRT runs without
    # changing the immutable project-owned session content.
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))

    reopened = CrtProject.open(project.root)
    reopened_record = reopened.session_by_path(path)
    assert reopened_record is not None
    reopened_repository = ProjectSearchIndex(reopened)
    reopened_fingerprint = reopened_repository.fingerprint(reopened, reopened_record)
    assert reopened_repository.is_current(reopened_fingerprint)

    data_result = QueryEngine().search(
        reopened_repository.source(reopened_fingerprint.source_id),
        SearchQuery("7F2735", fields=frozenset({"Dane"})),
    )
    assert [hit.row for hit in data_result.hits] == [2]


def test_persistent_index_resumes_from_last_committed_batch(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Resume search")
    frames = [
        CanFrame(index + 1, (index + 1) * 1_000, 0x100 + (index % 8), bytes((index & 0xFF,)))
        for index in range(2_100)
    ]
    path, record = _create_session(project, "resume", frames)
    repository = ProjectSearchIndex(project)
    cancel = Event()

    def progress(current: int, _total: int) -> None:
        if current >= 1_000:
            cancel.set()

    fingerprint = repository.rebuild_session(
        project,
        record,
        progress=progress,
        cancel_event=cancel,
        batch_size=1_000,
    )
    state = repository.state(fingerprint.source_id)
    assert state is not None
    assert state.status == "pending"
    assert state.indexed_rows == 1_000

    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))
    repository.rebuild_session(project, record, batch_size=1_000)
    final_state = repository.state(fingerprint.source_id)
    assert final_state is not None
    assert final_state.status == "ready"
    assert final_state.indexed_rows == len(frames)
    assert repository.is_current(repository.fingerprint(project, record, path))


def test_content_change_invalidates_index_and_session_removal_cleans_it(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Index cleanup")
    path, record = _create_session(
        project,
        "cleanup",
        [CanFrame(1, 1_000, 0x321, b"\x01")],
    )
    repository = ProjectSearchIndex(project)
    fingerprint = repository.rebuild_session(project, record)
    assert repository.is_current(fingerprint)

    # Metadata-only changes are accepted after SHA-256 verification.
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))
    touched = repository.fingerprint(project, record, path)
    assert repository.is_current(touched)

    # A same-size content mutation must still invalidate the index.
    original = path.read_bytes()
    mutated = original.replace(b'"data":"01"', b'"data":"02"', 1)
    assert mutated != original
    assert len(mutated) == len(original)
    path.write_bytes(mutated)
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))
    changed = repository.fingerprint(project, record, path)
    assert not repository.is_current(changed)

    remove_session(project, record.id, delete_files=True)
    assert repository.state(fingerprint.source_id) is None
    assert not path.exists()
