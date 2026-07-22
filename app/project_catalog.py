from __future__ import annotations

import json
import os
import platform
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Literal

from . import sqlite_connection as sqlite3

PROFILE_NAME = "project-profile.json"
CATALOG_NAME = "projects.sqlite"
PROJECT_MANIFEST_NAME = "project.crt.json"

ProjectTimeFilter = Literal["all", "30d", "7d", "yesterday", "today"]


@dataclass(frozen=True, slots=True)
class ProjectProfile:
    vehicle_brand: str = ""
    vehicle_model: str = ""
    production_year: int | None = None
    vehicle_type: str = ""
    vin: str = ""
    registration_number: str = ""
    customer_name: str = ""
    vehicle_notes: str = ""
    ecu_manufacturer: str = ""
    ecu_type: str = ""
    ecu_function: str = ""
    part_number: str = ""
    secondary_part_number: str = ""
    hardware_number: str = ""
    hardware_version: str = ""
    software_number: str = ""
    software_version: str = ""
    calibration_number: str = ""
    bootloader_version: str = ""
    ecu_serial_number: str = ""
    processor_type: str = ""
    ecu_status: str = ""
    fault_description: str = ""
    tags: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, payload: dict[str, object]) -> "ProjectProfile":
        allowed = {field.name for field in fields(cls)}
        values = {name: payload.get(name) for name in allowed if name in payload}
        raw_year = values.get("production_year")
        values["production_year"] = int(raw_year) if raw_year not in (None, "") else None
        raw_tags = values.get("tags", ())
        if isinstance(raw_tags, str):
            raw_tags = [part.strip() for part in raw_tags.split(",")]
        values["tags"] = tuple(str(tag).strip() for tag in raw_tags if str(tag).strip())
        return cls(**values)

    def normalized(self) -> "ProjectProfile":
        payload = asdict(self)
        for key, value in tuple(payload.items()):
            if isinstance(value, str):
                payload[key] = value.strip()
        year = payload["production_year"]
        if year is not None and not 1900 <= int(year) <= 2200:
            raise ValueError("production year must be between 1900 and 2200")
        payload["tags"] = tuple(
            dict.fromkeys(str(tag).strip() for tag in self.tags if str(tag).strip())
        )
        return ProjectProfile(**payload)


@dataclass(frozen=True, slots=True)
class CatalogProject:
    project_id: str
    root_path: str
    name: str
    description: str
    created_at_utc: str
    updated_at_utc: str
    last_opened_at_utc: str
    available: bool
    profile: ProjectProfile


class ProjectCatalog:
    """Application-wide index of portable CRT project folders."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path or default_catalog_path()).resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def register_project(
        self,
        project_root: str | Path,
        *,
        profile: ProjectProfile | None = None,
        opened: bool = False,
    ) -> CatalogProject:
        root = Path(project_root).resolve()
        manifest = _read_manifest(root)
        current_profile = (profile or load_project_profile(root)).normalized()
        save_project_profile(root, current_profile)
        now = _utc_now()
        opened_at = now if opened else str(manifest.get("created_at_utc", now))
        with sqlite3.connect(self.database_path) as connection:
            existing = connection.execute(
                "SELECT last_opened_at_utc FROM projects WHERE project_id = ?",
                (str(manifest["id"]),),
            ).fetchone()
            if existing is not None and not opened:
                opened_at = str(existing[0])
            connection.execute(
                """
                INSERT INTO projects(
                    project_id, root_path, name, description, created_at_utc,
                    updated_at_utc, last_opened_at_utc, available, profile_json,
                    search_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    root_path = excluded.root_path,
                    name = excluded.name,
                    description = excluded.description,
                    updated_at_utc = excluded.updated_at_utc,
                    last_opened_at_utc = excluded.last_opened_at_utc,
                    available = 1,
                    profile_json = excluded.profile_json,
                    search_text = excluded.search_text
                """,
                (
                    str(manifest["id"]),
                    str(root),
                    str(manifest.get("name", root.name)),
                    str(manifest.get("description", "")),
                    str(manifest["created_at_utc"]),
                    str(manifest.get("updated_at_utc", manifest["created_at_utc"])),
                    opened_at,
                    json.dumps(asdict(current_profile), ensure_ascii=False),
                    _search_text(manifest, current_profile),
                ),
            )
            connection.commit()
        return self.get(str(manifest["id"]))

    def mark_opened(self, project_id: str) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "UPDATE projects SET last_opened_at_utc = ? WHERE project_id = ?",
                (_utc_now(), project_id),
            )
            connection.commit()

    def remove(self, project_id: str) -> None:
        """Remove only the catalog entry; never delete the project directory."""
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
            connection.commit()

    def refresh_availability(self) -> None:
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute("SELECT project_id, root_path FROM projects").fetchall()
            for project_id, root_path in rows:
                available = int((Path(str(root_path)) / PROJECT_MANIFEST_NAME).is_file())
                connection.execute(
                    "UPDATE projects SET available = ? WHERE project_id = ?",
                    (available, str(project_id)),
                )
            connection.commit()

    def get(self, project_id: str) -> CatalogProject:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT project_id, root_path, name, description, created_at_utc,
                       updated_at_utc, last_opened_at_utc, available, profile_json
                FROM projects WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()
        if row is None:
            raise KeyError(project_id)
        return _row_to_project(row)

    def list_projects(
        self,
        *,
        query: str = "",
        time_filter: ProjectTimeFilter = "all",
        include_missing: bool = True,
    ) -> list[CatalogProject]:
        clauses: list[str] = []
        parameters: list[object] = []
        tokens = [token.casefold() for token in query.split() if token.strip()]
        for token in tokens:
            clauses.append("search_text LIKE ?")
            parameters.append(f"%{token}%")
        if not include_missing:
            clauses.append("available = 1")
        start, end = _time_bounds(time_filter)
        if start is not None:
            clauses.append("last_opened_at_utc >= ?")
            parameters.append(start.isoformat())
        if end is not None:
            clauses.append("last_opened_at_utc < ?")
            parameters.append(end.isoformat())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT project_id, root_path, name, description, created_at_utc,
                       updated_at_utc, last_opened_at_utc, available, profile_json
                FROM projects
                {where}
                ORDER BY last_opened_at_utc DESC, created_at_utc DESC,
                         name COLLATE NOCASE
                """,
                parameters,
            ).fetchall()
        return [_row_to_project(row) for row in rows]

    def _initialize(self) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS projects(
                    project_id TEXT PRIMARY KEY,
                    root_path TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    last_opened_at_utc TEXT NOT NULL,
                    available INTEGER NOT NULL DEFAULT 1,
                    profile_json TEXT NOT NULL,
                    search_text TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_projects_last_opened "
                "ON projects(last_opened_at_utc DESC)"
            )
            connection.commit()


def default_catalog_path() -> Path:
    override = os.environ.get("CRT_APP_DATA_DIR", "").strip()
    if override:
        root = Path(override).expanduser()
    elif platform.system() == "Windows":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "CANResearchTool"
    elif platform.system() == "Darwin":
        root = Path.home() / "Library" / "Application Support" / "CANResearchTool"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "can-research-tool"
    return root / CATALOG_NAME


def load_project_profile(project_root: str | Path) -> ProjectProfile:
    path = Path(project_root).resolve() / PROFILE_NAME
    if not path.is_file():
        return ProjectProfile()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("project profile must be a JSON object")
    return ProjectProfile.from_mapping(payload).normalized()


def save_project_profile(project_root: str | Path, profile: ProjectProfile) -> None:
    root = Path(project_root).resolve()
    if not (root / PROJECT_MANIFEST_NAME).is_file():
        raise ValueError("directory is not a CRT project")
    path = root / PROFILE_NAME
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(asdict(profile.normalized()), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _read_manifest(project_root: Path) -> dict[str, object]:
    path = project_root / PROJECT_MANIFEST_NAME
    if not path.is_file():
        raise ValueError(f"directory does not contain {PROJECT_MANIFEST_NAME}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not payload.get("id"):
        raise ValueError("invalid CRT project manifest")
    return payload


def _search_text(manifest: dict[str, object], profile: ProjectProfile) -> str:
    values: Iterable[object] = (
        manifest.get("name", ""),
        manifest.get("description", ""),
        *asdict(profile).values(),
    )
    flattened: list[str] = []
    for value in values:
        if isinstance(value, (tuple, list)):
            flattened.extend(str(item) for item in value)
        elif value is not None:
            flattened.append(str(value))
    return " ".join(flattened).casefold()


def _row_to_project(row: tuple[object, ...]) -> CatalogProject:
    return CatalogProject(
        project_id=str(row[0]),
        root_path=str(row[1]),
        name=str(row[2]),
        description=str(row[3]),
        created_at_utc=str(row[4]),
        updated_at_utc=str(row[5]),
        last_opened_at_utc=str(row[6]),
        available=bool(row[7]),
        profile=ProjectProfile.from_mapping(json.loads(str(row[8]))).normalized(),
    )


def _time_bounds(
    value: ProjectTimeFilter,
    *,
    now: datetime | None = None,
) -> tuple[datetime | None, datetime | None]:
    current = now or datetime.now(timezone.utc)
    start_today = current.replace(hour=0, minute=0, second=0, microsecond=0)
    if value == "all":
        return None, None
    if value == "30d":
        return current - timedelta(days=30), None
    if value == "7d":
        return current - timedelta(days=7), None
    if value == "today":
        return start_today, start_today + timedelta(days=1)
    if value == "yesterday":
        return start_today - timedelta(days=1), start_today
    raise ValueError(f"unsupported project time filter: {value}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "CATALOG_NAME",
    "PROFILE_NAME",
    "CatalogProject",
    "ProjectCatalog",
    "ProjectProfile",
    "ProjectTimeFilter",
    "default_catalog_path",
    "load_project_profile",
    "save_project_profile",
]
