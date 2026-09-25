"""Stage M v1, local-only export contracts. No capture or network dependencies."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path, PureWindowsPath
from typing import Any

from . import sqlite_connection as sqlite3
from .artifact_catalog import ArtifactCatalog, ArtifactIntegrityError
from .project import MANIFEST_NAME, PROJECT_FORMAT, PROJECT_VERSION, CrtProject, ProjectManifest
from .session_stream import iter_session_frames, read_session_header

EXPORT_SCHEMA = "crt.platform.session-export"
CONTEXT_SCHEMA = "crt.platform.ai-context"
FINDING_SCHEMA = "crt.platform.ai-finding"
SCHEMA_VERSION = 1
ALGORITHM_VERSION = "1"


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    """UTF-8, sorted keys, compact separators, no NaN, no trailing newline."""
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def content_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


@dataclass(frozen=True)
class FileReference:
    relative_path: str
    sha256: str
    bytes: int
    media_type: str
    role: str


class _ReadOnlyProject(CrtProject):
    def _connect(self):
        database = safe_path(self.root, ".crt/project.sqlite")
        wal = database.with_name(database.name + "-wal")
        if wal.exists() and wal.stat().st_size:
            raise ValueError("close project writers and checkpoint WAL before export")
        return sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True)


def safe_path(root: Path, relative: str) -> Path:
    """Reject traversal, absolute paths (including Windows), and escaping symlinks."""
    path = Path(relative)
    if (
        not relative
        or path.is_absolute()
        or PureWindowsPath(relative).drive
        or "\\" in relative
        or ".." in path.parts
    ):
        raise ValueError("expected a project-relative path without traversal")
    resolved = (root / path).resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError("file must be inside the project")
    return resolved


class PlatformExporter:
    """Read an existing project without migrations, indexes, or source writes.

    Callers must use a quiescent project. Concurrent file changes detected during
    hashing fail closed; this is not a transactional snapshot of live capture.
    """

    def __init__(self, root: str | Path):
        root = Path(root).resolve(strict=True)
        payload = json.loads(safe_path(root, MANIFEST_NAME).read_text(encoding="utf-8"))
        if payload.get("format") != PROJECT_FORMAT or payload.get("version") != PROJECT_VERSION:
            raise ValueError("unsupported CRT project manifest")
        self.project = _ReadOnlyProject(root, ProjectManifest(**payload))
        self.catalog = ArtifactCatalog(self.project)

    def file_reference(
        self,
        relative: str,
        *,
        role: str,
        media_type: str = "application/octet-stream",
        expected_hash: str = "",
    ) -> dict[str, Any]:
        path = safe_path(self.project.root, relative)
        digest = hashlib.sha256()
        before = path.stat()
        size = 0
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
                size += len(block)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ino,
        ) or size != before.st_size:
            raise ArtifactIntegrityError("file changed during export")
        actual = digest.hexdigest()
        if expected_hash and actual != expected_hash:
            raise ArtifactIntegrityError("source SHA-256 mismatch")
        return asdict(FileReference(Path(relative).as_posix(), actual, size, media_type, role))

    def manifest(self, session_id: str, *, artifact_ids: tuple[str, ...] = ()) -> dict[str, Any]:
        record = next((r for r in self.project.list_sessions() if r.id == session_id), None)
        if record is None:
            raise KeyError(f"unknown session: {session_id}")
        if record.status != "ready":
            raise ValueError("export requires a ready, quiescent session")
        source = self.file_reference(
            record.relative_path,
            role="raw_capture",
            media_type="application/x-ndjson",
            expected_hash=record.sha256,
        )
        path = safe_path(self.project.root, record.relative_path)
        header = read_session_header(path)
        count, lower, upper = 0, None, None
        for frame in iter_session_frames(path):
            count += 1
            lower = frame.timestamp_ns if lower is None else min(lower, frame.timestamp_ns)
            upper = frame.timestamp_ns if upper is None else max(upper, frame.timestamp_ns)
        self.file_reference(
            record.relative_path, role="raw_capture", expected_hash=source["sha256"]
        )
        files = [source]
        original = header.metadata.get("original_file")
        if original:
            files.append(
                self.file_reference(
                    original,
                    role="original_import",
                    media_type="text/csv",
                    expected_hash=header.metadata.get("original_sha256", ""),
                )
            )
        artifacts = []
        for artifact_id in sorted(set(artifact_ids)):
            artifact = self.catalog.get(artifact_id)
            if {s.session_id for s in artifact.sources} != {session_id}:
                raise ValueError("selected artifact must reference only the selected session")
            ref = self.file_reference(
                artifact.relative_path,
                role="analysis_artifact",
                media_type=artifact.metadata.get("media_type", "application/json"),
                expected_hash=artifact.sha256,
            )
            item = asdict(artifact)
            item.pop("relative_path")
            item["sha256"] = ref["sha256"]
            item["file"] = ref
            artifacts.append(item)
        mode = header.metadata.get("receive_mode")
        return {
            "schema_id": EXPORT_SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "algorithm_version": ALGORITHM_VERSION,
            "project_id": self.project.manifest.id,
            "session_id": record.id,
            "source": {
                "kind": record.source,
                "header_source": header.source,
                "started_at_utc": header.started_at_utc,
                "adapter": header.adapter,
                "bitrate": header.bitrate,
                "channel": header.channel,
            },
            "capture_mode": mode or "unknown",
            "time_bounds": {
                "min_timestamp_ns": lower,
                "max_timestamp_ns": upper,
                "clock": "source session clock; UTC correspondence unspecified",
            },
            "frame_count": count,
            "catalog_frame_count": record.frame_count,
            "files": files,
            "artifacts": artifacts,
            "provenance": {
                "session_schema_id": "crt-session-jsonl",
                "session_schema_version": 1,
                "decoder": "unknown; consult selected artifact provenance",
            },
            "omitted_data": [
                "unselected artifacts",
                "other sessions",
                "markers",
                "notes",
                "attachments",
                "unselected metadata",
                "decoder files",
            ],
            "limitations": [
                "local references only; file contents are not embedded",
                "capture mode is recorded metadata, not a hardware guarantee",
                "requires a quiescent project; not a live transactional snapshot",
            ],
        }

    def context(
        self,
        session_id: str,
        *,
        question: str,
        artifact_ids: tuple[str, ...] = (),
        maximum_bytes: int = 1024 * 1024,
    ) -> dict[str, Any]:
        if not question.strip() or maximum_bytes <= 0:
            raise ValueError("question and positive maximum_bytes are required")
        manifest = self.manifest(session_id, artifact_ids=artifact_ids)
        evidence = []
        for artifact in manifest["artifacts"]:
            path = safe_path(self.project.root, artifact["file"]["relative_path"])
            with path.open("rb") as handle:
                content = handle.read(maximum_bytes + 1)
            if len(content) > maximum_bytes:
                raise ValueError("selected artifact exceeds context byte limit")
            if hashlib.sha256(content).hexdigest() != artifact["sha256"]:
                raise ArtifactIntegrityError("artifact changed during context construction")
            evidence.append({"artifact": artifact, "selected_payload": json.loads(content)})
        package = {
            "schema_id": CONTEXT_SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "algorithm_version": ALGORITHM_VERSION,
            "project_id": manifest["project_id"],
            "session_id": session_id,
            "manifest_sha256": content_hash(manifest),
            "source_files": manifest["files"],
            "question": question,
            "evidence": evidence,
            "omitted_data": manifest["omitted_data"] + ["raw frame contents"],
            "limitations": manifest["limitations"] + ["AI output is advisory and requires review"],
            "maximum_bytes": maximum_bytes,
        }
        if len(canonical_bytes(package)) > maximum_bytes:
            raise ValueError("context package exceeds total byte limit")
        return package


def ai_finding(
    *, provider: str, model: str, context: dict[str, Any], title: str, description: str
) -> dict[str, Any]:
    """Artifact payload only: persist via ArtifactWriter, never update source facts."""
    if not all(value.strip() for value in (provider, model, title, description)):
        raise ValueError("provider, model, title and description are required")
    if context.get("schema_id") != CONTEXT_SCHEMA or context.get("schema_version") != 1:
        raise ValueError("unsupported context contract")
    return {
        "schema_id": FINDING_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "status": "suggested",
        "provider": provider,
        "model": model,
        "context_sha256": content_hash(context),
        "project_id": context["project_id"],
        "session_id": context["session_id"],
        "sources": context["source_files"],
        "artifacts": [
            {"id": e["artifact"]["id"], "sha256": e["artifact"]["sha256"]}
            for e in context["evidence"]
        ],
        "title": title,
        "description": description,
    }
