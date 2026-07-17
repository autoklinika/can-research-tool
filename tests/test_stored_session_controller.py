from __future__ import annotations

from pathlib import Path
from time import monotonic, sleep

from app.filters import FilterMode, FilterPreset, ProjectFilterRepository
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter
from app.stored_session_controller import (
    StoredSessionController,
    StoredSessionPageState,
)


def _project_with_session(tmp_path: Path) -> tuple[CrtProject, Path]:
    project = CrtProject.create(tmp_path / "project", name="Stored controller")
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

    path = project.live_sessions_dir / "stored.crt.jsonl"
    with SessionStreamWriter(
        CaptureSession(name="stored", source="test"),
        path,
        index_stride=2,
    ) as writer:
        for sequence, can_id in enumerate((0x100, 0x101, 0x100, 0x102, 0x100)):
            writer.append(
                CanFrame(
                    sequence=sequence,
                    timestamp_ns=sequence * 1_000_000,
                    arbitration_id=can_id,
                    data=bytes([sequence]),
                )
            )
    return project, path


def _await_page(controller: StoredSessionController) -> StoredSessionPageState:
    deadline = monotonic() + 5.0
    while monotonic() < deadline:
        state = controller.poll()
        if state is not None and not state.loading:
            return state
        sleep(0.005)
    raise AssertionError("stored-session page did not finish loading")


def test_controller_starts_unfiltered_and_returns_neutral_page_state(
    tmp_path: Path,
) -> None:
    _project, path = _project_with_session(tmp_path)
    controller = StoredSessionController(path, page_size=2)
    try:
        loading = controller.start()
        assert loading.loading is True
        assert loading.filters_enabled is False
        assert loading.available_filter_count == 1
        assert loading.active_filter_count == 0

        state = _await_page(controller)
        assert state.session_title == "stored"
        assert state.filter_affects_visibility is False
        assert state.page is not None
        assert state.page.total_frames == 5
        assert [frame.sequence for frame in state.page.frames] == [0, 1]
    finally:
        controller.shutdown()


def test_controller_owns_filter_opt_in_and_filtered_pagination(tmp_path: Path) -> None:
    _project, path = _project_with_session(tmp_path)
    controller = StoredSessionController(path, page_size=2)
    try:
        controller.start()
        _await_page(controller)

        loading = controller.set_filters_enabled(True)
        assert loading.filters_enabled is True
        assert loading.active_filter_names == ("Only 0x100",)
        filtered = _await_page(controller)
        assert filtered.filter_affects_visibility is True
        assert filtered.page is not None
        assert filtered.page.visible_frames == 3
        assert [frame.sequence for frame in filtered.page.frames] == [0, 2]

        next_loading = controller.next_page()
        assert next_loading is not None and next_loading.loading is True
        last = _await_page(controller)
        assert last.page_start == 2
        assert last.last_page_start == 2
        assert last.page is not None
        assert [frame.sequence for frame in last.page.frames] == [4]

        previous_loading = controller.previous_page()
        assert previous_loading is not None and previous_loading.loading is True
        first = _await_page(controller)
        assert first.page_start == 0
    finally:
        controller.shutdown()


def test_controller_discards_superseded_page_results(tmp_path: Path) -> None:
    _project, path = _project_with_session(tmp_path)
    controller = StoredSessionController(path, page_size=2)
    try:
        first = controller.start()
        second = controller.set_filters_enabled(True)
        assert second.generation > first.generation

        state = _await_page(controller)
        assert state.generation == second.generation
        assert state.filters_enabled is True
        assert state.page is not None
        assert [frame.sequence for frame in state.page.frames] == [0, 2]
    finally:
        controller.shutdown()
