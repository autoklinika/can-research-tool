from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
import sqlite3
import tempfile
from typing import Any

from app.domain import Artifact, ArtifactSource
from app.models import CanFrame

from ..contracts import AnalysisContext, SessionSource
from ..manifest import ExtensionManifest, ExtensionPermission, ExtensionType
from . import payload_difference as _stage2


PAYLOAD_DIFFERENCE_PROVIDER_ID = _stage2.PAYLOAD_DIFFERENCE_PROVIDER_ID
PAYLOAD_DIFFERENCE_PROVIDER_VERSION = "1.1.0"
PAYLOAD_DIFFERENCE_ALGORITHM_VERSION = "2"
PAYLOAD_DIFFERENCE_ARTIFACT_SCHEMA_VERSION = (
    _stage2.PAYLOAD_DIFFERENCE_ARTIFACT_SCHEMA_VERSION
)

_PROGRESS_STRIDE = 4096
_VARIANT_STORAGE_MODE = "adaptive_memory_sqlite_exact"
_VARIANT_SELECTION_RULE = "all_variants_exact"

MessageKey = tuple[int, int, bool, bool, bool]


class _ExactVariantStore:
    """Run-scoped SQLite spill store for exact payload variant counters."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._connection = sqlite3.connect(str(path))
        self._connection.execute("PRAGMA journal_mode=MEMORY")
        self._connection.execute("PRAGMA synchronous=OFF")
        self._connection.execute("PRAGMA temp_store=MEMORY")
        self._connection.execute(
            """
            CREATE TABLE variant_counts (
                namespace TEXT NOT NULL,
                payload BLOB NOT NULL,
                count INTEGER NOT NULL,
                first_timestamp_ns INTEGER,
                last_timestamp_ns INTEGER,
                PRIMARY KEY (namespace, payload)
            ) WITHOUT ROWID
            """
        )

    def __enter__(self) -> _ExactVariantStore:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def close(self) -> None:
        connection = self._connection
        if connection is None:
            return
        self._connection = None
        connection.close()

    def commit(self) -> None:
        self._require_connection().commit()

    def spill(
        self,
        namespace: str,
        variants: dict[bytes, _stage2._VariantStats],
    ) -> None:
        if not variants:
            return
        self._require_connection().executemany(
            """
            INSERT INTO variant_counts (
                namespace,
                payload,
                count,
                first_timestamp_ns,
                last_timestamp_ns
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                (
                    namespace,
                    sqlite3.Binary(payload),
                    stats.count,
                    stats.first_timestamp_ns,
                    stats.last_timestamp_ns,
                )
                for payload, stats in variants.items()
            ),
        )

    def add(self, namespace: str, payload: bytes, timestamp_ns: int) -> None:
        self._require_connection().execute(
            """
            INSERT INTO variant_counts (
                namespace,
                payload,
                count,
                first_timestamp_ns,
                last_timestamp_ns
            ) VALUES (?, ?, 1, ?, ?)
            ON CONFLICT(namespace, payload) DO UPDATE SET
                count = variant_counts.count + 1,
                last_timestamp_ns = excluded.last_timestamp_ns
            """,
            (
                namespace,
                sqlite3.Binary(payload),
                timestamp_ns,
                timestamp_ns,
            ),
        )

    def count(self, namespace: str) -> int:
        row = self._require_connection().execute(
            "SELECT COUNT(*) FROM variant_counts WHERE namespace = ?",
            (namespace,),
        ).fetchone()
        return 0 if row is None else int(row[0])

    def payloads(self, namespace: str, frame_count: int) -> list[dict[str, Any]]:
        rows = self._require_connection().execute(
            """
            SELECT payload, count, first_timestamp_ns, last_timestamp_ns
            FROM variant_counts
            WHERE namespace = ?
            ORDER BY count DESC, length(payload), hex(payload)
            """,
            (namespace,),
        )
        return [
            _variant_payload(
                bytes(payload),
                int(count),
                first_timestamp_ns,
                last_timestamp_ns,
                frame_count,
            )
            for payload, count, first_timestamp_ns, last_timestamp_ns in rows
        ]

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("exact payload variant store is closed")
        return self._connection


@dataclass(slots=True)
class _ExactMessagePayloadStats:
    namespace: str
    store: _ExactVariantStore
    memory_threshold: int
    frame_count: int = 0
    dlc_counts: Counter[int] = field(default_factory=Counter)
    tracked_variants: dict[bytes, _stage2._VariantStats] = field(
        default_factory=dict
    )
    byte_positions: list[_stage2._ByteStats] = field(default_factory=list)
    spilled_to_disk: bool = False

    @property
    def untracked_variant_frame_count(self) -> int:
        return 0

    def add(self, frame: CanFrame) -> None:
        self.frame_count += 1
        data = bytes(frame.data)
        self.dlc_counts[len(data)] += 1
        if self.spilled_to_disk:
            self.store.add(self.namespace, data, frame.timestamp_ns)
        else:
            variant = self.tracked_variants.get(data)
            if variant is not None:
                variant.add(frame.timestamp_ns)
            elif len(self.tracked_variants) < self.memory_threshold:
                variant = _stage2._VariantStats()
                variant.add(frame.timestamp_ns)
                self.tracked_variants[data] = variant
            else:
                self.store.spill(self.namespace, self.tracked_variants)
                self.tracked_variants.clear()
                self.spilled_to_disk = True
                self.store.add(self.namespace, data, frame.timestamp_ns)
        while len(self.byte_positions) < len(data):
            self.byte_positions.append(_stage2._ByteStats())
        for index, value in enumerate(data):
            self.byte_positions[index].add(value)

    def variant_count(self) -> int:
        if self.spilled_to_disk:
            return self.store.count(self.namespace)
        return len(self.tracked_variants)

    def payload(self) -> dict[str, Any]:
        variants = (
            self.store.payloads(self.namespace, self.frame_count)
            if self.spilled_to_disk
            else sorted(
                (
                    stats.payload(data, self.frame_count)
                    for data, stats in self.tracked_variants.items()
                ),
                key=lambda item: (
                    -int(item["count"]),
                    int(item["dlc"]),
                    str(item["payload_hex"]),
                ),
            )
        )
        byte_positions = [
            {"index": index, **stats.payload(self.frame_count)}
            for index, stats in enumerate(self.byte_positions)
        ]
        return {
            "frame_count": self.frame_count,
            "dlc_counts": [
                {
                    "dlc": dlc,
                    "count": count,
                    "share_percent": _stage2._round(
                        count * 100 / self.frame_count
                    ),
                }
                for dlc, count in sorted(self.dlc_counts.items())
            ],
            "variant_tracking": {
                "configured_limit": None,
                "memory_threshold": self.memory_threshold,
                "storage_mode": (
                    "sqlite" if self.spilled_to_disk else "memory"
                ),
                "spilled_to_disk": self.spilled_to_disk,
                "selection_rule": _VARIANT_SELECTION_RULE,
                "tracked_variant_count": len(variants),
                "tracked_variant_frame_count": self.frame_count,
                "untracked_variant_frame_count": 0,
                "complete": True,
            },
            "variants": variants,
            "byte_position_count": len(byte_positions),
            "constant_byte_position_count": sum(
                1
                for item in byte_positions
                if item["classification"] == "constant"
            ),
            "variable_byte_position_count": sum(
                1
                for item in byte_positions
                if item["classification"] == "variable"
            ),
            "byte_positions": byte_positions,
        }


@dataclass(slots=True)
class _ExactSessionPayloadStats:
    source: SessionSource
    store: _ExactVariantStore
    memory_threshold: int
    data_frame_count: int = 0
    skipped_non_data_frame_count: int = 0
    messages: dict[MessageKey, _ExactMessagePayloadStats] = field(
        default_factory=dict
    )

    def add(self, frame: CanFrame) -> None:
        if frame.is_remote_frame or frame.is_error_frame:
            self.skipped_non_data_frame_count += 1
            return
        self.data_frame_count += 1
        key = _stage2._message_key(frame)
        message = self.messages.get(key)
        if message is None:
            message = _ExactMessagePayloadStats(
                namespace=_variant_namespace(self.source.id, key),
                store=self.store,
                memory_threshold=self.memory_threshold,
            )
            self.messages[key] = message
        message.add(frame)

    def summary(
        self,
        baseline_keys: set[MessageKey],
        baseline_id: str,
    ) -> dict[str, Any]:
        own_keys = set(self.messages)
        is_base = self.source.id == baseline_id
        return {
            "id": self.source.id,
            "name": self.source.name,
            "source": self.source.source,
            "status": self.source.status,
            "role": "base" if is_base else "compared",
            "declared_frame_count": self.source.frame_count,
            "reader_frame_count": self.source.frames.frame_count,
            "observed_data_frame_count": self.data_frame_count,
            "skipped_non_data_frame_count": self.skipped_non_data_frame_count,
            "payload_message_key_count": len(self.messages),
            "new_payload_message_key_count": (
                0 if is_base else len(own_keys - baseline_keys)
            ),
            "missing_payload_message_key_count": (
                0 if is_base else len(baseline_keys - own_keys)
            ),
            "tracked_payload_variant_count": sum(
                message.variant_count() for message in self.messages.values()
            ),
            "untracked_payload_variant_frame_count": 0,
            "disk_backed_message_count": sum(
                1
                for message in self.messages.values()
                if message.spilled_to_disk
            ),
            "constant_byte_position_count": sum(
                sum(
                    1
                    for byte in message.byte_positions
                    if len(byte.values) == 1
                )
                for message in self.messages.values()
            ),
            "variable_byte_position_count": sum(
                sum(
                    1
                    for byte in message.byte_positions
                    if len(byte.values) > 1
                )
                for message in self.messages.values()
            ),
            "sha256": self.source.sha256,
        }


class PayloadDifferenceProvider:
    """Deterministic exact comparison with adaptive RAM/SQLite storage."""

    manifest = ExtensionManifest(
        id=PAYLOAD_DIFFERENCE_PROVIDER_ID,
        name="CAN payload differences",
        version=PAYLOAD_DIFFERENCE_PROVIDER_VERSION,
        crt_api="1",
        type=ExtensionType.COMPARISON,
        inputs=("comparison_set",),
        outputs=("payload_differences",),
        permissions=(
            ExtensionPermission.PROJECT_READ,
            ExtensionPermission.SESSION_READ,
            ExtensionPermission.ARTIFACT_WRITE,
        ),
    )
    algorithm_version = PAYLOAD_DIFFERENCE_ALGORITHM_VERSION

    def run(self, context: AnalysisContext) -> Artifact:
        analysis_input, comparison = _stage2._comparison_input(context)
        if comparison.synchronization_mode != "none":
            raise ValueError(
                "payload differences Stage 2.1 support only "
                "synchronization_mode none"
            )
        parameters = _stage2._parameters(analysis_input.parameters)
        memory_threshold = parameters["max_variants_per_message"]
        sources = tuple(
            context.project.session(session_id)
            for session_id in comparison.session_ids
        )
        total_work = sum(source.frames.frame_count for source in sources) + 1
        context.progress.report(
            0,
            total_work,
            "reading immutable payload sessions",
        )

        with _temporary_variant_directory() as temporary_directory:
            store_path = Path(temporary_directory) / "payload-variants.sqlite3"
            with _ExactVariantStore(store_path) as store:
                ordered = self._analyse_sources(
                    context,
                    sources,
                    store,
                    memory_threshold,
                    total_work,
                )
                store.commit()
                payload, artifact_sources, metadata = self._build_payload(
                    context,
                    analysis_input,
                    comparison,
                    ordered,
                    parameters,
                )

        artifact = context.artifact_writer.write_json(
            filename="payload-differences.json",
            artifact_type="payload_differences",
            schema_version=PAYLOAD_DIFFERENCE_ARTIFACT_SCHEMA_VERSION,
            sources=artifact_sources,
            payload=payload,
            metadata=metadata,
        )
        context.progress.report(
            total_work,
            total_work,
            "saved payload differences",
        )
        return artifact

    def _analyse_sources(
        self,
        context: AnalysisContext,
        sources: tuple[SessionSource, ...],
        store: _ExactVariantStore,
        memory_threshold: int,
        total_work: int,
    ) -> tuple[_ExactSessionPayloadStats, ...]:
        by_session: dict[str, _ExactSessionPayloadStats] = {}
        processed = 0
        for source in sources:
            stats = _ExactSessionPayloadStats(
                source=source,
                store=store,
                memory_threshold=memory_threshold,
            )
            for frame in source.frames.iter_frames():
                context.cancellation.raise_if_cancelled()
                stats.add(frame)
                processed += 1
                if processed % _PROGRESS_STRIDE == 0:
                    context.progress.report(
                        processed,
                        total_work,
                        f"analysed {processed} payload frames",
                    )
            by_session[source.id] = stats
            context.progress.report(
                processed,
                total_work,
                f"analysed payloads in session {source.name}",
            )
        return tuple(
            by_session[session_id]
            for session_id in context.comparison.session_ids
        )

    def _build_payload(
        self,
        context: AnalysisContext,
        analysis_input: Any,
        comparison: Any,
        ordered: tuple[_ExactSessionPayloadStats, ...],
        parameters: dict[str, Any],
    ) -> tuple[
        dict[str, Any],
        tuple[ArtifactSource, ...],
        dict[str, Any],
    ]:
        baseline_id = (
            comparison.base_session_id or comparison.session_ids[0]
        )
        by_session = {session.source.id: session for session in ordered}
        baseline = by_session[baseline_id]
        keys = sorted(
            {
                key
                for session in ordered
                for key in session.messages
            },
            key=_stage2._message_key_sort,
        )
        baseline_keys = set(baseline.messages)
        sessions = [
            session.summary(baseline_keys, baseline_id)
            for session in ordered
        ]
        (
            message_keys,
            notable,
            notable_count,
            change_counts,
        ) = _stage2._message_matrix(
            keys,
            ordered,
            baseline,
            parameters,
        )
        _normalize_variant_tracking(message_keys, parameters)
        tracked_variant_count = sum(
            message.variant_count()
            for session in ordered
            for message in session.messages.values()
        )
        disk_backed_message_count = sum(
            1
            for session in ordered
            for message in session.messages.values()
            if message.spilled_to_disk
        )
        public_parameters = {
            **parameters,
            "max_variants_semantics": "memory_spill_threshold",
            "variant_storage_mode": _VARIANT_STORAGE_MODE,
        }
        payload = {
            "schema": "crt.payload_differences",
            "schema_version": PAYLOAD_DIFFERENCE_ARTIFACT_SCHEMA_VERSION,
            "generated_by": {
                "provider_id": self.manifest.id,
                "provider_version": self.manifest.version,
                "algorithm_version": self.algorithm_version,
                "crt_api": self.manifest.crt_api,
            },
            "project": {
                "id": context.project.project_id,
                "name": context.project.project_name,
            },
            "input": {
                "kind": analysis_input.kind,
                "source_id": analysis_input.source_id,
                "parameters": public_parameters,
            },
            "comparison_set": {
                "id": comparison.id,
                "name": comparison.name,
                "session_ids": list(comparison.session_ids),
                "base_session_id": comparison.base_session_id,
                "effective_baseline_session_id": baseline_id,
                "synchronization_mode": comparison.synchronization_mode,
                "parameters": dict(comparison.parameters),
            },
            "summary": {
                "session_count": len(ordered),
                "baseline_session_id": baseline_id,
                "union_payload_message_key_count": len(keys),
                "common_payload_message_key_count": len(
                    set.intersection(
                        *(set(session.messages) for session in ordered)
                    )
                ),
                "tracked_payload_variant_count": tracked_variant_count,
                "constant_byte_change_count": change_counts[
                    "constant_byte_changed"
                ],
                "constant_variable_transition_count": (
                    change_counts["byte_became_variable"]
                    + change_counts["byte_became_constant"]
                ),
                "byte_value_set_change_count": change_counts[
                    "byte_value_set_changed"
                ],
                "notable_change_count": notable_count,
                "returned_notable_change_count": len(notable),
                "notable_changes_truncated": notable_count > len(notable),
                "change_type_counts": [
                    {"change_type": key, "count": count}
                    for key, count in sorted(change_counts.items())
                ],
            },
            "sessions": sessions,
            "message_payload_profiles": message_keys,
            "ranked_changes": notable,
            "variant_storage": {
                "mode": _VARIANT_STORAGE_MODE,
                "exact": True,
                "memory_variant_threshold": parameters[
                    "max_variants_per_message"
                ],
                "disk_backed_message_count": disk_backed_message_count,
                "temporary_database_persisted": False,
            },
            "truncation": {
                "variant_tracking_complete": True,
                "selection_rule": _VARIANT_SELECTION_RULE,
                "messages_with_truncated_variants": 0,
                "untracked_variant_frame_count": 0,
            },
        }
        artifact_sources = tuple(
            ArtifactSource(
                session_id=session.source.id,
                source_kind="session",
                source_reference={
                    "comparison_set_id": comparison.id,
                    "role": (
                        "base"
                        if session.source.id == baseline_id
                        else "comparison"
                    ),
                    "position": index,
                    "frame_count": session.source.frames.frame_count,
                    "data_frame_count": session.data_frame_count,
                    "sha256": session.source.sha256,
                },
            )
            for index, session in enumerate(ordered)
        )
        metadata = {
            "comparison_set_id": comparison.id,
            "baseline_session_id": baseline_id,
            "session_count": len(ordered),
            "payload_message_key_count": len(keys),
            "notable_change_count": notable_count,
            "variant_tracking_complete": True,
            "variant_storage_mode": _VARIANT_STORAGE_MODE,
            "disk_backed_message_count": disk_backed_message_count,
        }
        return payload, artifact_sources, metadata


def _variant_payload(
    data: bytes,
    count: int,
    first_timestamp_ns: int | None,
    last_timestamp_ns: int | None,
    frame_count: int,
) -> dict[str, Any]:
    return {
        "payload_hex": data.hex(" ").upper(),
        "dlc": len(data),
        "count": count,
        "share_percent": _stage2._round(count * 100 / frame_count),
        "first_timestamp_ns": first_timestamp_ns,
        "last_timestamp_ns": last_timestamp_ns,
    }


def _variant_namespace(session_id: str, key: MessageKey) -> str:
    channel, arbitration_id, extended, remote, error = key
    return (
        f"{session_id}|{channel}|{arbitration_id}|"
        f"{int(extended)}|{int(remote)}|{int(error)}"
    )


def _normalize_variant_tracking(
    message_keys: list[dict[str, Any]],
    parameters: dict[str, Any],
) -> None:
    threshold = parameters["max_variants_per_message"]
    for message in message_keys:
        profiles = [message.get("baseline")]
        profiles.extend(
            row.get("payload_profile")
            for row in message.get("sessions", [])
        )
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            tracking = profile.get("variant_tracking")
            if not isinstance(tracking, dict):
                continue
            tracking.update(
                {
                    "configured_limit": None,
                    "memory_threshold": threshold,
                    "selection_rule": _VARIANT_SELECTION_RULE,
                    "untracked_variant_frame_count": 0,
                    "complete": True,
                }
            )
        message["variant_matrix_complete"] = True


def _temporary_variant_directory():
    return tempfile.TemporaryDirectory(prefix="crt-payload-variants-")


__all__ = [
    "PAYLOAD_DIFFERENCE_ALGORITHM_VERSION",
    "PAYLOAD_DIFFERENCE_ARTIFACT_SCHEMA_VERSION",
    "PAYLOAD_DIFFERENCE_PROVIDER_ID",
    "PAYLOAD_DIFFERENCE_PROVIDER_VERSION",
    "PayloadDifferenceProvider",
]
