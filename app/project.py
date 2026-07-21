from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from kvaser.csv_import import iter_monitor_csv

from . import sqlite_connection as sqlite3
from .marker_stream import iter_markers, marker_path_for_session
from .markers import CaptureMarker, MarkerPreset
from .models import CaptureSession
from .session_stream import SessionPagedReader, SessionStreamWriter, read_session_header


PROJECT_FORMAT = "crt-project"
PROJECT_VERSION = 1
MANIFEST_NAME = "project.crt.json"


@dataclass(frozen=True, slots=True)
class ProjectManifest:
    id: str
    name: str
    description: str
    created_at_utc: str
    updated_at_utc: str
    default_bitrate: int = 250_000
    default_receive_mode: str = "bench"
    format: str = PROJECT_FORMAT
    version: int = PROJECT_VERSION


@dataclass(frozen=True, slots=True)
class SessionRecord:
    id: str
    name: str
    relative_path: str
    source: str
    status: str
    created_at_utc: str
    frame_count: int
    marker_count: int
    duration_s: float
    sha256: str


@dataclass(frozen=True, slots=True)
class StudyArea:
    id: str
    name: str
    description: str
    created_at_utc: str


class CrtProject:
    """Portable CRT project rooted in one self-contained directory."""

    _DIRECTORIES = (
        ".crt/indexes",
        "sessions/live",
        "sessions/imported/source",
        "experiments",
        "notes",
        "attachments",
        "decoders",
        "exports",
        "reports",
    )

    def __init__(self, root: str | Path, manifest: ProjectManifest) -> None:
        self.root = Path(root).resolve()
        self.manifest = manifest
        self.manifest_path = self.root / MANIFEST_NAME
        self.database_path = self.root / ".crt" / "project.sqlite"

    @classmethod
    def create(
        cls,
        root: str | Path,
        *,
        name: str,
        description: str = "",
        default_bitrate: int = 250_000,
        default_receive_mode: str = "bench",
    ) -> "CrtProject":
        project_root = Path(root).resolve()
        if project_root.exists():
            if not project_root.is_dir():
                raise ValueError("project path is not a directory")
            if any(project_root.iterdir()):
                raise ValueError("project directory must be empty")
        project_root.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        manifest = ProjectManifest(
            id=str(uuid4()),
            name=name.strip() or project_root.name,
            description=description.strip(),
            created_at_utc=now,
            updated_at_utc=now,
            default_bitrate=default_bitrate,
            default_receive_mode=default_receive_mode,
        )
        project = cls(project_root, manifest)
        project._ensure_layout()
        project._write_manifest()
        project._initialize_database()
        return project

    @classmethod
    def open(cls, root: str | Path) -> "CrtProject":
        project_root = Path(root).resolve()
        manifest_path = project_root / MANIFEST_NAME
        if not manifest_path.is_file():
            raise ValueError(f"selected directory does not contain {MANIFEST_NAME}")
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if payload.get("format") != PROJECT_FORMAT:
            raise ValueError("unsupported CRT project manifest")
        if int(payload.get("version", 0)) != PROJECT_VERSION:
            raise ValueError(f"unsupported CRT project version: {payload.get('version')}")
        manifest = ProjectManifest(
            id=str(payload["id"]),
            name=str(payload["name"]),
            description=str(payload.get("description", "")),
            created_at_utc=str(payload["created_at_utc"]),
            updated_at_utc=str(payload.get("updated_at_utc", payload["created_at_utc"])),
            default_bitrate=int(payload.get("default_bitrate", 250_000)),
            default_receive_mode=str(payload.get("default_receive_mode", "bench")),
            format=str(payload["format"]),
            version=int(payload["version"]),
        )
        project = cls(project_root, manifest)
        project._ensure_layout()
        project._initialize_database()
        return project

    @property
    def live_sessions_dir(self) -> Path:
        return self.root / "sessions" / "live"

    @property
    def imported_sessions_dir(self) -> Path:
        return self.root / "sessions" / "imported"

    def relative_path(self, path: str | Path) -> str:
        candidate = Path(path).resolve()
        try:
            return candidate.relative_to(self.root).as_posix()
        except ValueError as exc:
            raise ValueError("path is outside the CRT project") from exc

    def absolute_path(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("project-relative path escapes project directory") from exc
        return candidate

    def update_manifest(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        default_bitrate: int | None = None,
        default_receive_mode: str | None = None,
    ) -> None:
        self.manifest = ProjectManifest(
            id=self.manifest.id,
            name=self.manifest.name if name is None else name.strip(),
            description=self.manifest.description if description is None else description.strip(),
            created_at_utc=self.manifest.created_at_utc,
            updated_at_utc=datetime.now(timezone.utc).isoformat(),
            default_bitrate=(
                self.manifest.default_bitrate if default_bitrate is None else int(default_bitrate)
            ),
            default_receive_mode=(
                self.manifest.default_receive_mode
                if default_receive_mode is None
                else default_receive_mode
            ),
        )
        self._write_manifest()

    def list_sessions(self) -> list[SessionRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, relative_path, source, status, created_at_utc,
                       frame_count, marker_count, duration_s, sha256
                FROM sessions
                ORDER BY created_at_utc DESC, name COLLATE NOCASE
                """
            ).fetchall()
        return [SessionRecord(*row) for row in rows]

    def register_session(
        self,
        path: str | Path,
        *,
        name: str,
        source: str,
        status: str = "recording",
    ) -> SessionRecord:
        relative = self.relative_path(path)
        now = datetime.now(timezone.utc).isoformat()
        session_id = str(uuid4())
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT id, created_at_utc FROM sessions WHERE relative_path = ?",
                (relative,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO sessions(
                        id, name, relative_path, source, status, created_at_utc,
                        frame_count, marker_count, duration_s, sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0.0, '')
                    """,
                    (session_id, name, relative, source, status, now),
                )
                created_at = now
            else:
                session_id, created_at = str(existing[0]), str(existing[1])
                connection.execute(
                    "UPDATE sessions SET name = ?, source = ?, status = ? WHERE id = ?",
                    (name, source, status, session_id),
                )
            connection.commit()
        return SessionRecord(
            session_id,
            name,
            relative,
            source,
            status,
            created_at,
            0,
            0,
            0.0,
            "",
        )

    def finalize_session(
        self,
        path: str | Path,
        *,
        frame_count: int,
        marker_count: int,
        duration_s: float,
        status: str = "ready",
    ) -> None:
        absolute = Path(path).resolve()
        relative = self.relative_path(absolute)
        digest = _sha256(absolute) if absolute.is_file() else ""
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE sessions
                SET status = ?, frame_count = ?, marker_count = ?, duration_s = ?, sha256 = ?
                WHERE relative_path = ?
                """,
                (status, frame_count, marker_count, duration_s, digest, relative),
            )
            connection.commit()

    def session_by_path(self, path: str | Path) -> SessionRecord | None:
        relative = self.relative_path(path)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, name, relative_path, source, status, created_at_utc,
                       frame_count, marker_count, duration_s, sha256
                FROM sessions WHERE relative_path = ?
                """,
                (relative,),
            ).fetchone()
        return None if row is None else SessionRecord(*row)

    def list_study_areas(self) -> list[StudyArea]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, description, created_at_utc
                FROM study_areas ORDER BY name COLLATE NOCASE
                """
            ).fetchall()
        return [StudyArea(*row) for row in rows]

    def add_study_area(self, name: str, description: str = "") -> StudyArea:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("study area name cannot be empty")
        area = StudyArea(
            id=str(uuid4()),
            name=cleaned,
            description=description.strip(),
            created_at_utc=datetime.now(timezone.utc).isoformat(),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO study_areas(id, name, description, created_at_utc)
                VALUES (?, ?, ?, ?)
                """,
                (area.id, area.name, area.description, area.created_at_utc),
            )
            connection.commit()
        return area

    def link_session_to_area(self, session_id: str, area_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO area_sessions(area_id, session_id) VALUES (?, ?)",
                (area_id, session_id),
            )
            connection.commit()

    def area_session_ids(self, area_id: str) -> set[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT session_id FROM area_sessions WHERE area_id = ?",
                (area_id,),
            ).fetchall()
        return {str(row[0]) for row in rows}

    def list_marker_presets(self) -> list[MarkerPreset]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, shortcut, color, area, enabled, sort_order
                FROM marker_presets
                ORDER BY sort_order, name COLLATE NOCASE
                """
            ).fetchall()
        return [
            MarkerPreset(
                id=str(row[0]),
                name=str(row[1]),
                shortcut=str(row[2]),
                color=str(row[3]),
                area=str(row[4]),
                enabled=bool(row[5]),
                sort_order=int(row[6]),
            )
            for row in rows
        ]

    def save_marker_presets(self, presets: Iterable[MarkerPreset]) -> None:
        normalized = list(presets)
        shortcuts = [preset.shortcut.strip().lower() for preset in normalized if preset.enabled]
        if len(shortcuts) != len(set(shortcuts)):
            raise ValueError("active marker shortcuts must be unique")
        with self._connect() as connection:
            connection.execute("DELETE FROM marker_presets")
            connection.executemany(
                """
                INSERT INTO marker_presets(
                    id, name, shortcut, color, area, enabled, sort_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        preset.id,
                        preset.name,
                        preset.shortcut,
                        preset.color,
                        preset.area,
                        int(preset.enabled),
                        index,
                    )
                    for index, preset in enumerate(normalized)
                ],
            )
            connection.commit()

    def record_marker(self, session_path: str | Path, marker: CaptureMarker) -> None:
        session = self.session_by_path(session_path)
        if session is None:
            return
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO session_markers(
                    id, session_id, timestamp_ns, preset_id, name, shortcut,
                    color, area, source, note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    marker.id,
                    session.id,
                    marker.timestamp_ns,
                    marker.preset_id,
                    marker.name,
                    marker.shortcut,
                    marker.color,
                    marker.area,
                    marker.source,
                    marker.note,
                ),
            )
            connection.commit()

    def import_log(self, source_path: str | Path) -> SessionRecord:
        source = Path(source_path).resolve()
        if not source.is_file():
            raise FileNotFoundError(source)

        if source.name.lower().endswith(".crt.jsonl"):
            target = _unique_path(self.imported_sessions_dir / source.name)
            shutil.copy2(source, target)
            source_markers = marker_path_for_session(source)
            target_markers = marker_path_for_session(target)
            if source_markers.is_file():
                shutil.copy2(source_markers, target_markers)
            header = read_session_header(target)
            record = self.register_session(
                target,
                name=header.name or source.stem,
                source="imported-crt-session",
                status="ready",
            )
            reader = SessionPagedReader(target)
            marker_count = sum(1 for _ in iter_markers(target_markers))
            self.finalize_session(
                target,
                frame_count=reader.frame_count,
                marker_count=marker_count,
                duration_s=0.0,
            )
            return self.session_by_path(target) or record

        if source.suffix.lower() == ".csv":
            source_copy = _unique_path(self.imported_sessions_dir / "source" / source.name)
            shutil.copy2(source, source_copy)
            target = _unique_path(
                self.imported_sessions_dir / f"{_safe_filename(source.stem)}.crt.jsonl"
            )
            session = CaptureSession(
                name=source.stem,
                source="imported-kvaser-csv",
                metadata={
                    "original_file": self.relative_path(source_copy),
                    "original_sha256": _sha256(source_copy),
                },
            )
            frame_count = 0
            warning_count = 0
            writer = SessionStreamWriter(session, target)
            writer.open()
            try:
                for frame, warnings in iter_monitor_csv(source_copy):
                    writer.append(frame)
                    frame_count += 1
                    warning_count += len(warnings)
                writer.close(
                    {
                        "clean_close": True,
                        "frame_count": frame_count,
                        "import_warning_count": warning_count,
                    }
                )
            except Exception:
                writer.close({"clean_close": False, "frame_count": frame_count})
                raise
            record = self.register_session(
                target,
                name=source.stem,
                source="imported-kvaser-csv",
                status="ready",
            )
            self.finalize_session(
                target,
                frame_count=frame_count,
                marker_count=0,
                duration_s=0.0,
            )
            if warning_count:
                self._append_project_log(
                    f"Import {source.name}: {warning_count} ostrzeżeń parsera"
                )
            return self.session_by_path(target) or record

        raise ValueError("supported imports: *.crt.jsonl and Kvaser monitor *.csv")

    def _ensure_layout(self) -> None:
        for relative in self._DIRECTORIES:
            (self.root / relative).mkdir(parents=True, exist_ok=True)

    def _write_manifest(self) -> None:
        temporary = self.manifest_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(asdict(self.manifest), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.manifest_path)

    def _initialize_database(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS sessions(
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    relative_path TEXT NOT NULL UNIQUE,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    frame_count INTEGER NOT NULL DEFAULT 0,
                    marker_count INTEGER NOT NULL DEFAULT 0,
                    duration_s REAL NOT NULL DEFAULT 0.0,
                    sha256 TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS study_areas(
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    description TEXT NOT NULL DEFAULT '',
                    created_at_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS area_sessions(
                    area_id TEXT NOT NULL REFERENCES study_areas(id) ON DELETE CASCADE,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    PRIMARY KEY(area_id, session_id)
                );

                CREATE TABLE IF NOT EXISTS marker_presets(
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    shortcut TEXT NOT NULL,
                    color TEXT NOT NULL,
                    area TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    sort_order INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS session_markers(
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    timestamp_ns INTEGER NOT NULL,
                    preset_id TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL,
                    shortcut TEXT NOT NULL DEFAULT '',
                    color TEXT NOT NULL DEFAULT '',
                    area TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_created
                    ON sessions(created_at_utc);
                CREATE INDEX IF NOT EXISTS idx_markers_session_time
                    ON session_markers(session_id, timestamp_ns);
                """
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _append_project_log(self, text: str) -> None:
        path = self.root / ".crt" / "project.log"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now(timezone.utc).isoformat()} {text}\n")


def _safe_filename(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return sanitized or "session"


def _unique_path(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return path
    if path.name.lower().endswith(".crt.jsonl"):
        base = path.name[: -len(".crt.jsonl")]
        suffix = ".crt.jsonl"
    else:
        base = path.stem
        suffix = path.suffix
    index = 2
    while True:
        candidate = path.with_name(f"{base}_{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
