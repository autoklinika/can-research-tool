from __future__ import annotations

import hashlib

import pytest

from app.signal_hypothesis_review_service import SignalHypothesisReviewService
from app.signal_hypothesis_service import SignalHypothesisService
from tests.test_signal_hypothesis_ai import _FakeLocalAI, _build_candidate


def test_signal_hypothesis_review_is_append_only_and_operator_authoritative(tmp_path) -> None:
    project, comparison_id, candidate_artifact, session_hashes = _build_candidate(tmp_path)
    candidate_payload = SignalHypothesisService(project).artifacts.read_json(candidate_artifact)
    candidate_key = candidate_payload["candidates"][0]["candidate_key"]

    source_result = SignalHypothesisService(project, ai_client=_FakeLocalAI()).run(
        comparison_id,
        candidate_artifact_id=candidate_artifact.id,
        candidate_key=candidate_key,
    )
    source = source_result.artifacts[0]
    source_path = project.absolute_path(source.relative_path)
    source_sha_before = _sha256(source_path)
    source_payload = SignalHypothesisService(project).read_hypothesis(source)
    original = source_payload["hypothesis"]

    review = SignalHypothesisReviewService(project)
    editable = _editable(original)

    verified_result = review.run(
        comparison_id,
        hypothesis_artifact_id=source.id,
        action="verify",
        operator_hypothesis=editable,
        operator_note="Potwierdzono po powtórzeniu eksperymentu.",
    )
    verified_artifact = verified_result.artifacts[0]
    verified = review.read_review(verified_artifact)
    assert verified["schema"] == "crt.signal_hypothesis_review"
    assert verified["schema_version"] == 1
    assert verified["source_hypothesis"]["artifact_id"] == source.id
    assert verified["source_hypothesis"]["artifact_sha256"] == source.sha256
    assert verified["review"]["status"] == "verified"
    assert verified["review"]["verified"] is True
    assert verified["review"]["rejected"] is False
    assert verified["review"]["edited"] is False
    assert verified["review"]["edited_fields"] == []
    assert verified["effective_hypothesis"]["name"] == original["name"]
    assert verified["guardrails"]["append_only"] is True
    assert verified["guardrails"]["source_hypothesis_modified"] is False
    assert verified["guardrails"]["ai_used_for_review"] is False
    assert verified["guardrails"]["raw_session_access"] is False
    assert verified["guardrails"]["can_tx"] is False

    edited_fields = dict(editable)
    edited_fields["name"] = "EGR_related_state_candidate"
    edited_fields["physical_meaning"] = (
        "Operator opisuje kandydat jako stan związany z eksperymentem EGR; "
        "znaczenie 0/1 pozostaje nieustalone."
    )
    edited_fields["unit"] = "state"
    edited_result = review.run(
        comparison_id,
        hypothesis_artifact_id=source.id,
        action="edit",
        operator_hypothesis=edited_fields,
        operator_note="Edycja nazwy i opisu przed dodatkową weryfikacją.",
    )
    edited = review.read_review(edited_result.artifacts[0])
    assert edited["review"]["status"] == "edited"
    assert edited["review"]["verified"] is False
    assert edited["review"]["edited"] is True
    assert set(edited["review"]["edited_fields"]) == {
        "name",
        "physical_meaning",
        "unit",
    }
    assert edited["effective_hypothesis"]["name"] == "EGR_related_state_candidate"
    assert edited["effective_hypothesis"]["unit"] == "state"

    reverified_result = review.run(
        comparison_id,
        hypothesis_artifact_id=source.id,
        action="verify",
        operator_hypothesis=edited_fields,
        operator_note="Potwierdzono edytowaną treść po dodatkowym teście.",
    )
    reverified = review.read_review(reverified_result.artifacts[0])
    assert reverified["review"]["status"] == "verified"
    assert reverified["review"]["verified"] is True
    assert reverified["review"]["edited"] is True
    assert reverified["effective_hypothesis"]["name"] == "EGR_related_state_candidate"

    reviews = review.list_review_artifacts(
        comparison_id,
        hypothesis_artifact_id=source.id,
    )
    assert len(reviews) == 3
    latest = review.latest_review(comparison_id, source.id)
    assert latest is not None
    assert latest.id == reverified_result.artifacts[0].id

    assert _sha256(source_path) == source_sha_before == source.sha256
    source_after = SignalHypothesisService(project).read_hypothesis(source)
    assert source_after == source_payload
    for session_id, expected in session_hashes.items():
        record = next(item for item in project.list_sessions() if item.id == session_id)
        assert _sha256(project.absolute_path(record.relative_path)) == expected


def test_signal_hypothesis_reject_requires_reason_and_keeps_history(tmp_path) -> None:
    project, comparison_id, candidate_artifact, _hashes = _build_candidate(tmp_path)
    candidate_payload = SignalHypothesisService(project).artifacts.read_json(candidate_artifact)
    candidate_key = candidate_payload["candidates"][0]["candidate_key"]
    source = SignalHypothesisService(project, ai_client=_FakeLocalAI()).run(
        comparison_id,
        candidate_artifact_id=candidate_artifact.id,
        candidate_key=candidate_key,
    ).artifacts[0]

    review = SignalHypothesisReviewService(project)
    with pytest.raises(Exception, match="operator_note is required"):
        review.run(
            comparison_id,
            hypothesis_artifact_id=source.id,
            action="reject",
            operator_note="",
        )
    assert review.list_review_artifacts(
        comparison_id,
        hypothesis_artifact_id=source.id,
    ) == ()

    result = review.run(
        comparison_id,
        hypothesis_artifact_id=source.id,
        action="reject",
        operator_note="Korelacja jest prawdziwa, ale proponowane znaczenie nie przeszło testu odwrotnego.",
    )
    payload = review.read_review(result.artifacts[0])
    assert payload["review"]["status"] == "rejected"
    assert payload["review"]["verified"] is False
    assert payload["review"]["rejected"] is True
    assert payload["review"]["operator_note"].startswith("Korelacja jest prawdziwa")


def test_signal_hypothesis_edit_requires_actual_change(tmp_path) -> None:
    project, comparison_id, candidate_artifact, _hashes = _build_candidate(tmp_path)
    candidate_payload = SignalHypothesisService(project).artifacts.read_json(candidate_artifact)
    candidate_key = candidate_payload["candidates"][0]["candidate_key"]
    source = SignalHypothesisService(project, ai_client=_FakeLocalAI()).run(
        comparison_id,
        candidate_artifact_id=candidate_artifact.id,
        candidate_key=candidate_key,
    ).artifacts[0]
    source_payload = SignalHypothesisService(project).read_hypothesis(source)

    review = SignalHypothesisReviewService(project)
    with pytest.raises(Exception, match="edit requires at least one changed"):
        review.run(
            comparison_id,
            hypothesis_artifact_id=source.id,
            action="edit",
            operator_hypothesis=_editable(source_payload["hypothesis"]),
            operator_note="Bez zmian.",
        )
    assert review.list_review_artifacts(
        comparison_id,
        hypothesis_artifact_id=source.id,
    ) == ()


def _editable(hypothesis: dict) -> dict[str, object]:
    return {
        "name": hypothesis.get("name", ""),
        "physical_meaning": hypothesis.get("physical_meaning", ""),
        "unit": hypothesis.get("unit"),
        "scale": hypothesis.get("scale"),
        "offset": hypothesis.get("offset"),
        "rationale": hypothesis.get("rationale", ""),
    }


def _sha256(path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
