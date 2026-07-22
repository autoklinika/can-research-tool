from __future__ import annotations

import tempfile

import pytest

from app.comparison_analysis_service import ComparisonAnalysisService
from app.comparison_sets import ComparisonSetStore
from app.extensions import (
    PAYLOAD_DIFFERENCE_ALGORITHM_VERSION,
    PAYLOAD_DIFFERENCE_PROVIDER_ID,
    CancellationToken,
    ExtensionCancelled,
)
from app.extensions.builtin import payload_difference_exact
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter


def test_default_payload_storage_is_exact_beyond_1000_variants(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Exact variants")
    before = _create_session(project, "before", range(0, 1005))
    after = _create_session(project, "after", range(1, 1006))
    comparison = ComparisonSetStore(project).create(
        name="Exact variants",
        session_ids=(before.id, after.id),
        base_session_id=before.id,
    )
    service = ComparisonAnalysisService(project)

    first = service.run(PAYLOAD_DIFFERENCE_PROVIDER_ID, comparison.id)
    second = service.run(PAYLOAD_DIFFERENCE_PROVIDER_ID, comparison.id)
    first_payload = service.artifacts.read_json(first.artifacts[0])
    second_payload = service.artifacts.read_json(second.artifacts[0])

    assert first_payload == second_payload
    assert first.artifacts[0].sha256 == second.artifacts[0].sha256
    assert first_payload["generated_by"]["algorithm_version"] == (
        PAYLOAD_DIFFERENCE_ALGORITHM_VERSION
    )
    assert first_payload["summary"]["tracked_payload_variant_count"] == 2010
    assert first_payload["variant_storage"] == {
        "mode": "adaptive_memory_sqlite_exact",
        "exact": True,
        "memory_variant_threshold": 1000,
        "disk_backed_message_count": 2,
        "temporary_database_persisted": False,
    }
    assert first_payload["truncation"] == {
        "variant_tracking_complete": True,
        "selection_rule": "all_variants_exact",
        "messages_with_truncated_variants": 0,
        "untracked_variant_frame_count": 0,
    }

    changes = first_payload["ranked_changes"]
    assert _has_payload_change(
        changes,
        change_type="missing_payload_variant",
        payload_hex="00 00",
    )
    assert _has_payload_change(
        changes,
        change_type="new_payload_variant",
        payload_hex="03 ED",
    )
    assert not any(
        item["change_type"] == "variant_comparison_truncated"
        for item in changes
    )

    profile = first_payload["message_payload_profiles"][0]
    assert profile["variant_matrix_complete"] is True
    assert len(profile["variant_matrix"]) == 1006
    baseline_tracking = profile["baseline"]["variant_tracking"]
    assert baseline_tracking["configured_limit"] is None
    assert baseline_tracking["memory_threshold"] == 1000
    assert baseline_tracking["storage_mode"] == "sqlite"
    assert baseline_tracking["tracked_variant_count"] == 1005
    assert baseline_tracking["tracked_variant_frame_count"] == 1005
    assert baseline_tracking["untracked_variant_frame_count"] == 0
    assert baseline_tracking["complete"] is True


def test_temporary_variant_database_is_removed_after_cancellation(
    tmp_path,
    monkeypatch,
) -> None:
    project = CrtProject.create(tmp_path / "project", name="Cancelled exact variants")
    before = _create_session(project, "before", range(0, 1100))
    after = _create_session(project, "after", range(0, 1100))
    comparison = ComparisonSetStore(project).create(
        name="Cancelled exact variants",
        session_ids=(before.id, after.id),
        base_session_id=before.id,
    )
    temporary_root = tmp_path / "temporary-variant-store"
    temporary_root.mkdir()
    monkeypatch.setattr(
        payload_difference_exact,
        "_temporary_variant_directory",
        lambda: tempfile.TemporaryDirectory(
            prefix="crt-payload-variants-",
            dir=temporary_root,
        ),
    )
    cancellation = CancellationToken()

    def cancel_on_start(_update) -> None:
        cancellation.cancel()

    with pytest.raises(ExtensionCancelled):
        ComparisonAnalysisService(project).run(
            PAYLOAD_DIFFERENCE_PROVIDER_ID,
            comparison.id,
            cancellation=cancellation,
            progress_callback=cancel_on_start,
        )

    assert list(temporary_root.iterdir()) == []
    with project._connect() as connection:
        state = connection.execute(
            "SELECT status, error FROM analysis_runs "
            "ORDER BY created_at_utc DESC LIMIT 1"
        ).fetchone()
    assert state == ("cancelled", "cancelled by user")


def _create_session(project: CrtProject, name: str, values: range):
    path = project.live_sessions_dir / f"{name}.crt.jsonl"
    capture = CaptureSession(
        name=name,
        source="test",
        bitrate=250_000,
        channel=0,
    )
    writer = SessionStreamWriter(capture, path)
    writer.open()
    count = 0
    for sequence, value in enumerate(values):
        writer.append(
            CanFrame(
                sequence=sequence,
                timestamp_ns=sequence,
                arbitration_id=0x100,
                data=value.to_bytes(2, "big"),
                channel=0,
                is_extended_id=False,
            )
        )
        count += 1
    writer.close({"clean_close": True})
    record = project.register_session(
        path,
        name=name,
        source="test",
        status="ready",
    )
    project.finalize_session(
        path,
        frame_count=count,
        marker_count=0,
        duration_s=(count - 1) / 1_000_000_000.0,
    )
    return project.session_by_path(path) or record


def _has_payload_change(
    changes: list[dict],
    *,
    change_type: str,
    payload_hex: str,
) -> bool:
    return any(
        item["arbitration_id"] == 0x100
        and item["change_type"] == change_type
        and item.get("payload_hex") == payload_hex
        for item in changes
    )
