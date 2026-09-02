from __future__ import annotations

import hashlib
import os
import tempfile
from gc import collect
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.comparison_sets import ComparisonSetStore
from app.experiment_diff_service import ExperimentDiffService
from app.marker_stream import MarkerStreamWriter, marker_path_for_session
from app.markers import CaptureMarker, MarkerPreset
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter
from app.signal_candidate_service import SignalCandidateService
from app.signal_hypothesis_review_service import SignalHypothesisReviewService
from app.signal_hypothesis_service import SignalHypothesisService
from gui.signal_hypothesis_view import SignalHypothesisView
from tests_gui.signal_hypothesis_smoke import _FakeLocalAI, _drain


def main() -> int:
    app = QApplication.instance() or QApplication([])

    with tempfile.TemporaryDirectory() as directory:
        project = CrtProject.create(Path(directory) / "project", name="Hypothesis Review GUI")
        target = MarkerPreset.create("EGR disconnected", "F3")
        control = MarkerPreset.create("Control", "F4")
        first = _session(project, "first", target, control, 12, 14)
        second = _session(project, "second", target, control, 16, 18)
        comparison = ComparisonSetStore(project).create(
            name="Review correlation",
            session_ids=(first.id, second.id),
            base_session_id=first.id,
        )

        experiment = ExperimentDiffService(project)
        options = experiment.marker_options(comparison.id)
        target_option = next(item for item in options if item.preset_id == target.id)
        control_option = next(item for item in options if item.preset_id == control.id)
        experiment.run(
            comparison.id,
            target_selector=target_option.selector,
            control_selector=control_option.selector,
            pre_window_ms=30,
            post_window_ms=50,
        )
        candidate_artifact = SignalCandidateService(project).run(comparison.id).artifacts[0]
        candidate_payload = SignalHypothesisService(project).artifacts.read_json(candidate_artifact)
        candidate_key = candidate_payload["candidates"][0]["candidate_key"]
        source = SignalHypothesisService(project, ai_client=_FakeLocalAI()).run(
            comparison.id,
            candidate_artifact_id=candidate_artifact.id,
            candidate_key=candidate_key,
        ).artifacts[0]
        source_path = project.absolute_path(source.relative_path)
        source_hash = _sha256(source_path)

        view = SignalHypothesisView(project, comparison)
        view.show()
        _drain(app)
        assert view.hypothesis_combo.count() == 1
        assert view.review_verify_button.isEnabled()
        assert view.review_edit_button.isEnabled()
        assert view.review_reject_button.isEnabled()
        assert "brak" in view.review_status_label.text().lower()

        original_name = view.review_name_edit.text()
        assert original_name
        view.review_name_edit.setText("operator_edited_candidate")
        view.review_note_edit.setText("Edycja robocza operatora.")
        view.review_edit_button.click()
        _drain(app)

        review = SignalHypothesisReviewService(project)
        reviews = review.list_review_artifacts(
            comparison.id,
            hypothesis_artifact_id=source.id,
        )
        assert len(reviews) == 1
        edited = review.read_review(reviews[0])
        assert edited["review"]["status"] == "edited"
        assert edited["effective_hypothesis"]["name"] == "operator_edited_candidate"
        assert "EDYCJA ZAPISANA" in view.review_status_label.text()
        assert _sha256(source_path) == source_hash == source.sha256

        view.review_note_edit.setText("Potwierdzono po dodatkowym eksperymencie.")
        view.review_verify_button.click()
        _drain(app)
        reviews = review.list_review_artifacts(
            comparison.id,
            hypothesis_artifact_id=source.id,
        )
        assert len(reviews) == 2
        verified = review.read_review(reviews[0])
        assert verified["review"]["status"] == "verified"
        assert verified["review"]["verified"] is True
        assert verified["effective_hypothesis"]["name"] == "operator_edited_candidate"
        assert "POTWIERDZONA" in view.review_status_label.text()
        assert "historia: 2 decyzji" in view.review_status_label.text()
        assert _sha256(source_path) == source_hash

        view.review_note_edit.clear()
        view.review_reject_button.click()
        _drain(app)
        assert "wymaga krótkiego powodu" in view.review_status_label.text()
        assert len(
            review.list_review_artifacts(
                comparison.id,
                hypothesis_artifact_id=source.id,
            )
        ) == 2

        view.review_note_edit.setText("Test odwrotny obalił znaczenie semantyczne.")
        view.review_reject_button.click()
        _drain(app)
        reviews = review.list_review_artifacts(
            comparison.id,
            hypothesis_artifact_id=source.id,
        )
        assert len(reviews) == 3
        rejected = review.read_review(reviews[0])
        assert rejected["review"]["status"] == "rejected"
        assert rejected["review"]["rejected"] is True
        assert "ODRZUCONA" in view.review_status_label.text()
        assert "historia: 3 decyzji" in view.review_status_label.text()
        assert _sha256(source_path) == source_hash

        view.close()
        _drain(app)
        del view
        del project
        collect()
    return 0


def _session(
    project: CrtProject,
    name: str,
    target: MarkerPreset,
    control: MarkerPreset,
    first_delay_ms: int,
    second_delay_ms: int,
):
    path = project.live_sessions_dir / f"{name}.crt.jsonl"
    capture = CaptureSession(name=name, source="test", bitrate=250_000, channel=0)
    frames = (
        _frame(0, 90_000_000, b"\x00"),
        _frame(1, (100 + first_delay_ms) * 1_000_000, b"\x04"),
        _frame(2, 190_000_000, b"\x04"),
        _frame(3, 220_000_000, b"\x04"),
        _frame(4, 290_000_000, b"\x00"),
        _frame(5, (300 + second_delay_ms) * 1_000_000, b"\x04"),
    )
    writer = SessionStreamWriter(capture, path)
    writer.open()
    for frame in frames:
        writer.append(frame)
    writer.close({"clean_close": True, "frame_count": len(frames)})
    record = project.register_session(path, name=name, source="test", status="ready")
    project.finalize_session(path, frame_count=6, marker_count=3, duration_s=0.32)

    markers = MarkerStreamWriter(marker_path_for_session(path), presets=(target, control))
    markers.open()
    markers.append(CaptureMarker.from_preset(target, 100_000_000, source="test"))
    markers.append(CaptureMarker.from_preset(control, 200_000_000, source="test"))
    markers.append(CaptureMarker.from_preset(target, 300_000_000, source="test"))
    markers.close()
    return project.session_by_path(path) or record


def _frame(sequence: int, timestamp_ns: int, data: bytes) -> CanFrame:
    return CanFrame(
        sequence=sequence,
        timestamp_ns=timestamp_ns,
        arbitration_id=0x123,
        data=data,
        channel=0,
        is_extended_id=False,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
