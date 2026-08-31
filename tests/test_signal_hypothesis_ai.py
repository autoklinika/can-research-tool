from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.comparison_sets import ComparisonSetStore
from app.experiment_diff_service import ExperimentDiffService
from app.local_ai import (
    LocalAICompletion,
    LocalAIConfig,
    LocalAIUnavailable,
    extract_json_object,
)
from app.marker_stream import MarkerStreamWriter, marker_path_for_session
from app.markers import CaptureMarker, MarkerPreset
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter
from app.signal_candidate_service import SignalCandidateService
from app.signal_hypothesis_service import SignalHypothesisService


class _FakeLocalAI:
    def __init__(self, *, fail: bool = False) -> None:
        self._config = LocalAIConfig(
            base_url="http://127.0.0.1:11434/v1",
            model="fake-qwen",
            timeout_s=5,
        )
        self.fail = fail
        self.requests: list[dict[str, str]] = []

    @property
    def config(self) -> LocalAIConfig:
        return self._config

    def complete(self, *, system_prompt: str, user_prompt: str, cancellation=None):
        if cancellation is not None:
            cancellation.raise_if_cancelled()
        self.requests.append({"system": system_prompt, "user": user_prompt})
        if self.fail:
            raise LocalAIUnavailable("synthetic offline")
        return LocalAICompletion(
            provider="fake-local",
            model="fake-qwen",
            endpoint="http://127.0.0.1:11434/v1/chat/completions",
            content=json.dumps(
                {
                    "name": "EGR_state_candidate",
                    "physical_meaning": "Możliwy binarny stan związany z eksperymentem EGR.",
                    "unit": None,
                    "scale": None,
                    "offset": None,
                    "confidence": 0.82,
                    "rationale": "Bit zmienia się konsekwentnie po markerze testowym i nie zmienia się przy kontroli.",
                    "next_experiments": [
                        "Powtórz test EGR w przeciwnym stanie i sprawdź zmianę 1->0.",
                        "Dodaj drugi niezależny marker kontrolny.",
                    ],
                    "warnings": ["Nazwa markera nie jest dowodem znaczenia fizycznego."],
                },
                ensure_ascii=False,
            ),
            latency_ms=12.5,
            usage={"prompt_tokens": 100, "completion_tokens": 80},
        )


def test_signal_hypothesis_uses_only_candidate_artifact_and_keeps_source_truth(
    tmp_path: Path,
) -> None:
    project, comparison_id, candidate_artifact, hashes = _build_candidate(tmp_path)
    candidate_service = SignalCandidateService(project)
    candidate_payload = candidate_service.read_artifact(candidate_artifact)
    candidate = candidate_payload["candidates"][0]
    assert candidate["candidate_score"] == pytest.approx(1.0)

    fake = _FakeLocalAI()
    service = SignalHypothesisService(project, ai_client=fake)
    result = service.run(
        comparison_id,
        candidate_artifact_id=candidate_artifact.id,
        candidate_key=candidate["candidate_key"],
        user_context="Marker oznaczał fizyczne odłączenie EGR; traktuj jako wskazówkę, nie dowód.",
    )

    assert len(result.artifacts) == 1
    artifact = result.artifacts[0]
    assert artifact.artifact_type == "signal_hypothesis"
    payload = service.read_hypothesis(artifact)
    assert payload["schema"] == "crt.signal_hypothesis"
    assert payload["source_candidate"]["artifact_id"] == candidate_artifact.id
    assert payload["source_candidate"]["artifact_sha256"] == candidate_artifact.sha256
    assert payload["source_candidate"]["candidate_key"] == "0:STD:123:data:B0.2"
    assert payload["source_candidate"]["candidate_score"] == pytest.approx(1.0)
    assert payload["source_candidate"]["strength"] == "strong"

    hypothesis = payload["hypothesis"]
    assert hypothesis["status"] == "suggested"
    assert hypothesis["verified"] is False
    assert hypothesis["ai_generated"] is True
    assert hypothesis["name"] == "EGR_state_candidate"
    assert hypothesis["unit"] is None
    assert hypothesis["scale"] is None
    assert hypothesis["offset"] is None
    assert hypothesis["confidence"] == pytest.approx(0.82)
    assert len(hypothesis["next_experiments"]) == 2

    assert payload["guardrails"] == {
        "source_of_truth": "signal_candidates",
        "candidate_score_modified": False,
        "raw_session_access": False,
        "can_tx": False,
        "active_diagnostics": False,
        "automatic_confirmation": False,
        "ai_failure_blocks_crt": False,
    }
    assert payload["context_sent_to_ai"]["raw_session_included"] is False
    assert payload["context_sent_to_ai"]["evidence_events_included"] == 6
    assert payload["ai"]["provider"] == "fake-local"
    assert payload["ai"]["model"] == "fake-qwen"

    assert len(fake.requests) == 1
    sent = json.loads(fake.requests[0]["user"])
    assert set(sent) == {
        "task",
        "candidate_artifact",
        "candidate",
        "evidence",
        "operator_context",
    }
    assert sent["candidate"]["candidate_score"] == pytest.approx(1.0)
    assert sent["candidate"]["candidate_key"] == "0:STD:123:data:B0.2"
    assert len(sent["evidence"]) == 6
    assert "session" not in sent
    assert "frames" not in sent
    assert "raw" not in sent

    candidate_after = candidate_service.read_artifact(candidate_artifact)
    assert candidate_after == candidate_payload
    for session_id, expected in hashes.items():
        record = next(item for item in project.list_sessions() if item.id == session_id)
        assert _sha256(project.absolute_path(record.relative_path)) == expected


def test_signal_hypothesis_ai_failure_creates_no_hypothesis_and_does_not_block_catalog(
    tmp_path: Path,
) -> None:
    project, comparison_id, candidate_artifact, hashes = _build_candidate(tmp_path)
    candidate_payload = SignalCandidateService(project).read_artifact(candidate_artifact)
    candidate_key = candidate_payload["candidates"][0]["candidate_key"]
    service = SignalHypothesisService(project, ai_client=_FakeLocalAI(fail=True))

    with pytest.raises(Exception, match="synthetic offline"):
        service.run(
            comparison_id,
            candidate_artifact_id=candidate_artifact.id,
            candidate_key=candidate_key,
        )

    assert service.list_hypothesis_artifacts(comparison_id) == ()
    assert service.list_candidate_artifacts(comparison_id)
    for session_id, expected in hashes.items():
        record = next(item for item in project.list_sessions() if item.id == session_id)
        assert _sha256(project.absolute_path(record.relative_path)) == expected


def test_local_ai_stage1_rejects_public_endpoint_and_extracts_fenced_json() -> None:
    with pytest.raises(ValueError, match="public AI endpoints"):
        LocalAIConfig(base_url="https://api.example.com/v1", model="qwen")

    private = LocalAIConfig(base_url="http://192.168.1.55:11434/v1", model="qwen")
    assert private.base_url == "http://192.168.1.55:11434/v1"
    assert extract_json_object("```json\n{\"name\": \"x\"}\n```") == {"name": "x"}


def _build_candidate(tmp_path: Path):
    project = CrtProject.create(tmp_path / "project", name="Signal Hypothesis")
    target = MarkerPreset.create("EGR disconnected", "F3")
    control = MarkerPreset.create("Control", "F4")
    first = _create_session(project, "first", target, control, 12, 14)
    second = _create_session(project, "second", target, control, 16, 18)
    comparison = ComparisonSetStore(project).create(
        name="EGR A/B",
        session_ids=(first.id, second.id),
        base_session_id=first.id,
    )
    hashes = {
        first.id: _sha256(project.absolute_path(first.relative_path)),
        second.id: _sha256(project.absolute_path(second.relative_path)),
    }
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
    candidate_result = SignalCandidateService(project).run(comparison.id)
    return project, comparison.id, candidate_result.artifacts[0], hashes


def _create_session(
    project: CrtProject,
    name: str,
    target: MarkerPreset,
    control: MarkerPreset,
    first_target_delay_ms: int,
    second_target_delay_ms: int,
):
    session_path = project.live_sessions_dir / f"{name}.crt.jsonl"
    capture = CaptureSession(name=name, source="test", bitrate=250_000, channel=0)
    frames = (
        _frame(0, 90_000_000, b"\x00"),
        _frame(1, (100 + first_target_delay_ms) * 1_000_000, b"\x04"),
        _frame(2, 190_000_000, b"\x04"),
        _frame(3, 220_000_000, b"\x04"),
        _frame(4, 290_000_000, b"\x00"),
        _frame(5, (300 + second_target_delay_ms) * 1_000_000, b"\x04"),
    )
    writer = SessionStreamWriter(capture, session_path)
    writer.open()
    for frame in frames:
        writer.append(frame)
    writer.close({"clean_close": True, "frame_count": len(frames)})
    record = project.register_session(session_path, name=name, source="test", status="ready")
    project.finalize_session(
        session_path,
        frame_count=len(frames),
        marker_count=3,
        duration_s=0.32,
    )
    markers = MarkerStreamWriter(marker_path_for_session(session_path), presets=(target, control))
    markers.open()
    markers.append(CaptureMarker.from_preset(target, 100_000_000, source="test"))
    markers.append(CaptureMarker.from_preset(control, 200_000_000, source="test"))
    markers.append(CaptureMarker.from_preset(target, 300_000_000, source="test"))
    markers.close()
    return project.session_by_path(session_path) or record


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
