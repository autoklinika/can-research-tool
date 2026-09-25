import hashlib
import json

import pytest

from app.artifact_catalog import ArtifactIntegrityError
from app.domain import AnalysisInput, ArtifactSource
from app.extensions import ArtifactWriter, CancellationToken
from app.models import CanFrame, CaptureSession
from app.platform_export import PlatformExporter, ai_finding, canonical_bytes, content_hash
from app.platform_export_cli import main
from app.project import CrtProject
from app.project_domain_store import ProjectDomainStore
from app.session_stream import SessionStreamWriter


@pytest.fixture
def fixture(tmp_path):
    project = CrtProject.create(tmp_path / "project", name="Stage M")
    path = project.live_sessions_dir / "capture.crt.jsonl"
    writer = SessionStreamWriter(
        CaptureSession(name="capture", source="test", metadata={"receive_mode": "silent"}), path
    )
    writer.open()
    writer.append(CanFrame(0, 30, 123, b"\x01"))
    writer.append(CanFrame(1, 20, 123, b"\x02"))
    writer.close()
    record = project.register_session(path, name="capture", source="test", status="ready")
    project.finalize_session(path, frame_count=2, marker_count=0, duration_s=0.0)
    store = ProjectDomainStore(project)
    run = store.create_analysis_run(
        provider_id="crt.test",
        provider_version="1",
        algorithm_version="2",
        inputs=(AnalysisInput("session", record.id),),
    )
    artifact = ArtifactWriter(
        project=project,
        store=store,
        analysis_run_id=run.id,
        provider_id=run.provider_id,
        provider_version="1",
        algorithm_version="2",
        cancellation=CancellationToken(),
    ).write_json(
        filename="stats.json",
        artifact_type="statistics",
        schema_version=1,
        sources=(ArtifactSource(record.id, "session", {}),),
        payload={"count": 2},
    )
    return project, record, artifact


def snapshot(root):
    return {
        p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in root.rglob("*")
        if p.is_file()
    }


def test_export_is_deterministic_and_read_only(fixture):
    project, record, artifact = fixture
    before = snapshot(project.root)
    exporter = PlatformExporter(project.root)
    result = exporter.manifest(record.id, artifact_ids=(artifact.id,))
    assert canonical_bytes(result) == canonical_bytes(
        exporter.manifest(record.id, artifact_ids=(artifact.id, artifact.id))
    )
    assert result["project_id"] == project.manifest.id
    assert result["session_id"] == record.id
    assert result["frame_count"] == 2
    assert result["time_bounds"]["min_timestamp_ns"] == 20
    assert result["time_bounds"]["max_timestamp_ns"] == 30
    assert result["capture_mode"] == "silent"
    assert result["artifacts"][0]["algorithm_version"] == "2"
    for ref in result["files"]:
        data = (project.root / ref["relative_path"]).read_bytes()
        assert ref["sha256"] == hashlib.sha256(data).hexdigest()
        assert ref["bytes"] == len(data)
    assert snapshot(project.root) == before


def test_context_selection_limits_and_finding(fixture):
    project, record, artifact = fixture
    exporter = PlatformExporter(project.root)
    assert exporter.context(record.id, question="why?")["evidence"] == []
    context = exporter.context(record.id, question="why?", artifact_ids=(artifact.id,))
    assert context["evidence"][0]["selected_payload"] == {"count": 2}
    assert "raw frame contents" in context["omitted_data"]
    finding = ai_finding(
        provider="provider",
        model="model",
        context=context,
        title="Candidate",
        description="Needs review",
    )
    assert finding["status"] == "suggested"
    assert finding["context_sha256"] == content_hash(context)
    assert finding["artifacts"] == [{"id": artifact.id, "sha256": artifact.sha256}]
    with pytest.raises(ValueError, match="limit"):
        exporter.context(record.id, question="why?", artifact_ids=(artifact.id,), maximum_bytes=10)
    with pytest.raises(ValueError):
        exporter.context(record.id, question=" ")


@pytest.mark.parametrize(
    "relative",
    ["../outside", "sessions/../project.crt.json", "/etc/passwd", "C:/secret", "..\\secret"],
)
def test_rejects_unsafe_paths(fixture, relative):
    project, _, _ = fixture
    with pytest.raises(ValueError):
        PlatformExporter(project.root).file_reference(relative, role="test")


def test_rejects_escaping_symlink(fixture, tmp_path):
    project, _, _ = fixture
    outside = tmp_path / "outside"
    outside.write_text("secret")
    (project.root / "escape").symlink_to(outside)
    with pytest.raises(ValueError):
        PlatformExporter(project.root).file_reference("escape", role="test")


@pytest.mark.parametrize("target", ["session", "artifact"])
def test_rejects_tampered_evidence(fixture, target):
    project, record, artifact = fixture
    relative = record.relative_path if target == "session" else artifact.relative_path
    with (project.root / relative).open("ab") as handle:
        handle.write(b" ")
    with pytest.raises(ArtifactIntegrityError):
        PlatformExporter(project.root).manifest(record.id, artifact_ids=(artifact.id,))


def test_rejects_unknown_and_recording_session(fixture):
    project, record, _ = fixture
    exporter = PlatformExporter(project.root)
    with pytest.raises(KeyError):
        exporter.manifest("missing")
    with project._connect() as connection:
        connection.execute("UPDATE sessions SET status = 'recording' WHERE id = ?", (record.id,))
    with pytest.raises(ValueError, match="ready"):
        exporter.manifest(record.id)


def test_cli(fixture, capsys):
    project, record, artifact = fixture
    assert main([str(project.root), record.id]) == 0
    assert json.loads(capsys.readouterr().out)["schema_id"] == "crt.platform.session-export"
    assert (
        main(
            [str(project.root), record.id, "--artifact", artifact.id, "--question", "Explain count"]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["evidence"][0]["selected_payload"] == {"count": 2}


def test_empty_session_and_unknown_mode(tmp_path):
    project = CrtProject.create(tmp_path / "project", name="empty")
    path = project.live_sessions_dir / "empty.crt.jsonl"
    writer = SessionStreamWriter(CaptureSession(name="empty", source="test"), path)
    writer.open()
    writer.close()
    record = project.register_session(path, name="empty", source="test", status="ready")
    result = PlatformExporter(project.root).manifest(record.id)
    assert result["frame_count"] == 0
    assert result["time_bounds"]["min_timestamp_ns"] is None
    assert result["time_bounds"]["max_timestamp_ns"] is None
    assert result["capture_mode"] == "unknown"


def test_rejects_cross_session_artifact(fixture):
    project, record, artifact = fixture
    other = project.register_session(
        project.live_sessions_dir / "other.crt.jsonl", name="other", source="test", status="ready"
    )
    with project._connect() as connection:
        connection.execute(
            "UPDATE artifact_sources SET session_id = ? WHERE artifact_id = ?",
            (other.id, artifact.id),
        )
    with pytest.raises(ValueError, match="only the selected session"):
        PlatformExporter(project.root).context(
            record.id, question="why?", artifact_ids=(artifact.id,)
        )


def test_rejects_uncheckpointed_database(fixture):
    project, record, _ = fixture
    with project._connect() as connection:
        connection.execute("UPDATE sessions SET name = 'pending' WHERE id = ?", (record.id,))
        connection.commit()
        with pytest.raises(ValueError, match="checkpoint WAL"):
            PlatformExporter(project.root).manifest(record.id)


def test_original_import_file_is_hashed(tmp_path):
    project = CrtProject.create(tmp_path / "project", name="import")
    original = project.root / "sessions/imported/source/input.csv"
    original.write_text("original evidence")
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    path = project.imported_sessions_dir / "converted.crt.jsonl"
    writer = SessionStreamWriter(
        CaptureSession(
            name="import",
            source="imported",
            metadata={"original_file": project.relative_path(original), "original_sha256": digest},
        ),
        path,
    )
    writer.open()
    writer.close()
    record = project.register_session(path, name="import", source="imported", status="ready")
    result = PlatformExporter(project.root).manifest(record.id)
    assert result["files"][1]["role"] == "original_import"
    assert result["files"][1]["sha256"] == digest
    original.write_text("changed")
    with pytest.raises(ArtifactIntegrityError):
        PlatformExporter(project.root).manifest(record.id)
