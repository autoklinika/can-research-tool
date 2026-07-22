from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Iterator

from app.domain import Artifact, ArtifactSource
from app.models import CanFrame

from ..contracts import AnalysisContext, ComparisonContext, SessionSource
from ..manifest import ExtensionManifest, ExtensionPermission, ExtensionType


MESSAGE_SEQUENCE_PROVIDER_ID = "crt.comparison.message_sequences"
MESSAGE_SEQUENCE_PROVIDER_VERSION = "1.0.0"
MESSAGE_SEQUENCE_ALGORITHM_VERSION = "1"
MESSAGE_SEQUENCE_ARTIFACT_SCHEMA_VERSION = 1

_PROGRESS_STRIDE = 4096
_DEFAULT_MAXIMUM_RANKED_CHANGES = 500
_MAXIMUM_RANKED_CHANGES_LIMIT = 5000
_DEFAULT_OCCURRENCE_THRESHOLD_PERCENT = 10.0
_DEFAULT_SHARE_THRESHOLD_PERCENTAGE_POINTS = 0.5
_DEFAULT_MEAN_SPAN_THRESHOLD_PERCENT = 20.0
_DEFAULT_MEMORY_SEQUENCE_THRESHOLD = 50_000
_MAXIMUM_MEMORY_SEQUENCE_THRESHOLD = 1_000_000
_SEQUENCE_LENGTHS = (2, 3)
_SEQUENCE_MODES = ("raw", "collapsed")

MessageKey = tuple[int, int, bool, bool, bool]
BufferedKey = tuple[str, tuple[MessageKey, ...]]
Event = tuple[MessageKey, int, int]


@dataclass(slots=True)
class _SequenceStats:
    count: int = 0
    first_start_row: int | None = None
    last_start_row: int | None = None
    first_timestamp_ns: int | None = None
    last_timestamp_ns: int | None = None
    min_span_ns: int | None = None
    max_span_ns: int | None = None
    span_sum_ns: int = 0

    def add(
        self,
        *,
        start_row: int,
        start_timestamp_ns: int,
        end_timestamp_ns: int,
    ) -> None:
        span_ns = end_timestamp_ns - start_timestamp_ns
        if self.count == 0:
            self.first_start_row = start_row
            self.first_timestamp_ns = start_timestamp_ns
            self.min_span_ns = span_ns
            self.max_span_ns = span_ns
        self.count += 1
        self.last_start_row = start_row
        self.last_timestamp_ns = start_timestamp_ns
        self.min_span_ns = (
            span_ns if self.min_span_ns is None else min(self.min_span_ns, span_ns)
        )
        self.max_span_ns = (
            span_ns if self.max_span_ns is None else max(self.max_span_ns, span_ns)
        )
        self.span_sum_ns += span_ns


class _SequenceStore:
    """Run-scoped exact SQLite store with bounded in-memory batching."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._connection: sqlite3.Connection | None = sqlite3.connect(str(path))
        connection = self._require_connection()
        connection.execute("PRAGMA journal_mode=MEMORY")
        connection.execute("PRAGMA synchronous=OFF")
        connection.execute("PRAGMA temp_store=MEMORY")
        connection.execute(
            """
            CREATE TABLE sequence_stats (
                session_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                sequence_length INTEGER NOT NULL,
                sequence_key TEXT NOT NULL,
                is_cycle INTEGER NOT NULL,
                is_self_transition INTEGER NOT NULL,
                count INTEGER NOT NULL,
                first_start_row INTEGER NOT NULL,
                last_start_row INTEGER NOT NULL,
                first_timestamp_ns INTEGER NOT NULL,
                last_timestamp_ns INTEGER NOT NULL,
                min_span_ns INTEGER NOT NULL,
                max_span_ns INTEGER NOT NULL,
                span_sum_ns INTEGER NOT NULL,
                PRIMARY KEY (
                    session_id,
                    mode,
                    sequence_length,
                    sequence_key
                )
            ) WITHOUT ROWID
            """
        )
        connection.execute(
            """
            CREATE INDEX sequence_union_idx
            ON sequence_stats(mode, sequence_length, sequence_key, session_id)
            """
        )

    def __enter__(self) -> _SequenceStore:
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

    def upsert(
        self,
        session_id: str,
        entries: dict[BufferedKey, _SequenceStats],
    ) -> None:
        if not entries:
            return
        self._require_connection().executemany(
            """
            INSERT INTO sequence_stats (
                session_id,
                mode,
                sequence_length,
                sequence_key,
                is_cycle,
                is_self_transition,
                count,
                first_start_row,
                last_start_row,
                first_timestamp_ns,
                last_timestamp_ns,
                min_span_ns,
                max_span_ns,
                span_sum_ns
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(
                session_id,
                mode,
                sequence_length,
                sequence_key
            ) DO UPDATE SET
                count = sequence_stats.count + excluded.count,
                first_start_row = MIN(
                    sequence_stats.first_start_row,
                    excluded.first_start_row
                ),
                last_start_row = MAX(
                    sequence_stats.last_start_row,
                    excluded.last_start_row
                ),
                first_timestamp_ns = MIN(
                    sequence_stats.first_timestamp_ns,
                    excluded.first_timestamp_ns
                ),
                last_timestamp_ns = MAX(
                    sequence_stats.last_timestamp_ns,
                    excluded.last_timestamp_ns
                ),
                min_span_ns = MIN(
                    sequence_stats.min_span_ns,
                    excluded.min_span_ns
                ),
                max_span_ns = MAX(
                    sequence_stats.max_span_ns,
                    excluded.max_span_ns
                ),
                span_sum_ns = sequence_stats.span_sum_ns + excluded.span_sum_ns
            """,
            (
                (
                    session_id,
                    mode,
                    len(items),
                    _encode_sequence(items),
                    int(len(items) >= 3 and items[0] == items[-1]),
                    int(len(items) == 2 and items[0] == items[1]),
                    stats.count,
                    stats.first_start_row,
                    stats.last_start_row,
                    stats.first_timestamp_ns,
                    stats.last_timestamp_ns,
                    stats.min_span_ns,
                    stats.max_span_ns,
                    stats.span_sum_ns,
                )
                for (mode, items), stats in entries.items()
            ),
        )

    def unique_counts(self, session_id: str) -> dict[tuple[str, int], int]:
        rows = self._require_connection().execute(
            """
            SELECT mode, sequence_length, COUNT(*)
            FROM sequence_stats
            WHERE session_id = ?
            GROUP BY mode, sequence_length
            """,
            (session_id,),
        )
        return {
            (str(mode), int(length)): int(count)
            for mode, length, count in rows
        }

    def unique_cycle_count(self, session_id: str) -> int:
        row = self._require_connection().execute(
            """
            SELECT COUNT(*)
            FROM sequence_stats
            WHERE session_id = ? AND is_cycle = 1
            """,
            (session_id,),
        ).fetchone()
        return 0 if row is None else int(row[0])

    def new_missing_counts(
        self,
        session_id: str,
        baseline_id: str,
    ) -> tuple[int, int]:
        connection = self._require_connection()
        new_row = connection.execute(
            """
            SELECT COUNT(*)
            FROM sequence_stats AS current
            LEFT JOIN sequence_stats AS baseline
              ON baseline.session_id = ?
             AND baseline.mode = current.mode
             AND baseline.sequence_length = current.sequence_length
             AND baseline.sequence_key = current.sequence_key
            WHERE current.session_id = ?
              AND baseline.sequence_key IS NULL
            """,
            (baseline_id, session_id),
        ).fetchone()
        missing_row = connection.execute(
            """
            SELECT COUNT(*)
            FROM sequence_stats AS baseline
            LEFT JOIN sequence_stats AS current
              ON current.session_id = ?
             AND current.mode = baseline.mode
             AND current.sequence_length = baseline.sequence_length
             AND current.sequence_key = baseline.sequence_key
            WHERE baseline.session_id = ?
              AND current.sequence_key IS NULL
            """,
            (session_id, baseline_id),
        ).fetchone()
        return (
            0 if new_row is None else int(new_row[0]),
            0 if missing_row is None else int(missing_row[0]),
        )

    def union_unique_count(self) -> int:
        row = self._require_connection().execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT DISTINCT mode, sequence_length, sequence_key
                FROM sequence_stats
            )
            """
        ).fetchone()
        return 0 if row is None else int(row[0])

    def grouped_rows(self) -> Iterator[tuple[Any, ...]]:
        return iter(
            self._require_connection().execute(
                """
                SELECT
                    mode,
                    sequence_length,
                    sequence_key,
                    is_cycle,
                    is_self_transition,
                    session_id,
                    count,
                    first_start_row,
                    last_start_row,
                    first_timestamp_ns,
                    last_timestamp_ns,
                    min_span_ns,
                    max_span_ns,
                    span_sum_ns
                FROM sequence_stats
                ORDER BY
                    CASE mode WHEN 'raw' THEN 0 ELSE 1 END,
                    sequence_length,
                    sequence_key,
                    session_id
                """
            )
        )

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("message sequence store is closed")
        return self._connection


@dataclass(slots=True)
class _SessionSequenceStats:
    source: SessionSource
    store: _SequenceStore
    memory_sequence_threshold: int
    include_non_data_frames: bool
    observed_frame_count: int = 0
    skipped_non_data_frame_count: int = 0
    raw_event_count: int = 0
    collapsed_event_count: int = 0
    _raw_window: deque[Event] = field(default_factory=lambda: deque(maxlen=3))
    _collapsed_window: deque[Event] = field(
        default_factory=lambda: deque(maxlen=3)
    )
    _last_collapsed_key: MessageKey | None = None
    _buffer: dict[BufferedKey, _SequenceStats] = field(default_factory=dict)
    flush_count: int = 0

    def add(self, frame: CanFrame, source_row: int) -> None:
        if (
            not self.include_non_data_frames
            and (frame.is_remote_frame or frame.is_error_frame)
        ):
            self.skipped_non_data_frame_count += 1
            return
        key = _message_key(frame)
        event = (key, source_row, frame.timestamp_ns)
        self.observed_frame_count += 1
        self.raw_event_count += 1
        self._append_event("raw", self._raw_window, event)

        if key != self._last_collapsed_key:
            self.collapsed_event_count += 1
            self._append_event("collapsed", self._collapsed_window, event)
            self._last_collapsed_key = key

        if len(self._buffer) >= self.memory_sequence_threshold:
            self.flush()

    def flush(self) -> None:
        if not self._buffer:
            return
        self.store.upsert(self.source.id, self._buffer)
        self._buffer.clear()
        self.flush_count += 1

    def occurrence_total(self, mode: str, length: int) -> int:
        event_count = (
            self.raw_event_count
            if mode == "raw"
            else self.collapsed_event_count
        )
        return max(event_count - length + 1, 0)

    def _append_event(
        self,
        mode: str,
        window: deque[Event],
        event: Event,
    ) -> None:
        window.append(event)
        values = tuple(window)
        for length in _SEQUENCE_LENGTHS:
            if len(values) < length:
                continue
            occurrence = values[-length:]
            items = tuple(item[0] for item in occurrence)
            stats = self._buffer.setdefault((mode, items), _SequenceStats())
            stats.add(
                start_row=occurrence[0][1],
                start_timestamp_ns=occurrence[0][2],
                end_timestamp_ns=occurrence[-1][2],
            )


class MessageSequenceComparisonProvider:
    """Compare exact adjacent CAN message sequences in immutable session order."""

    manifest = ExtensionManifest(
        id=MESSAGE_SEQUENCE_PROVIDER_ID,
        name="CAN message sequence comparison",
        version=MESSAGE_SEQUENCE_PROVIDER_VERSION,
        crt_api="1",
        type=ExtensionType.COMPARISON,
        inputs=("comparison_set",),
        outputs=("message_sequence_differences",),
        permissions=(
            ExtensionPermission.PROJECT_READ,
            ExtensionPermission.SESSION_READ,
            ExtensionPermission.ARTIFACT_WRITE,
        ),
    )
    algorithm_version = MESSAGE_SEQUENCE_ALGORITHM_VERSION

    def run(self, context: AnalysisContext) -> Artifact:
        analysis_input, comparison = _comparison_input(context)
        if comparison.synchronization_mode != "none":
            raise ValueError(
                "message sequence Stage 3 supports only "
                "synchronization_mode none"
            )
        parameters = _parameters(analysis_input.parameters)
        sources = tuple(
            context.project.session(session_id)
            for session_id in comparison.session_ids
        )
        total_work = sum(source.frames.frame_count for source in sources) + 1
        context.progress.report(
            0,
            total_work,
            "reading immutable message sequences",
        )

        with tempfile.TemporaryDirectory(
            prefix="crt-message-sequences-"
        ) as temporary:
            store_path = Path(temporary) / "message-sequences.sqlite3"
            with _SequenceStore(store_path) as store:
                ordered = self._analyse_sources(
                    context,
                    sources,
                    store,
                    parameters,
                    total_work,
                )
                for session in ordered:
                    session.flush()
                store.commit()
                payload, artifact_sources, metadata = self._build_payload(
                    context,
                    analysis_input,
                    comparison,
                    ordered,
                    store,
                    parameters,
                )

        artifact = context.artifact_writer.write_json(
            filename="message-sequence-differences.json",
            artifact_type="message_sequence_differences",
            schema_version=MESSAGE_SEQUENCE_ARTIFACT_SCHEMA_VERSION,
            sources=artifact_sources,
            payload=payload,
            metadata=metadata,
        )
        context.progress.report(
            total_work,
            total_work,
            "saved message sequence differences",
        )
        return artifact

    def _analyse_sources(
        self,
        context: AnalysisContext,
        sources: tuple[SessionSource, ...],
        store: _SequenceStore,
        parameters: dict[str, Any],
        total_work: int,
    ) -> tuple[_SessionSequenceStats, ...]:
        by_session: dict[str, _SessionSequenceStats] = {}
        processed = 0
        for source in sources:
            stats = _SessionSequenceStats(
                source=source,
                store=store,
                memory_sequence_threshold=parameters[
                    "memory_sequence_threshold"
                ],
                include_non_data_frames=parameters[
                    "include_non_data_frames"
                ],
            )
            for source_row, frame in enumerate(source.frames.iter_frames()):
                context.cancellation.raise_if_cancelled()
                stats.add(frame, source_row)
                processed += 1
                if processed % _PROGRESS_STRIDE == 0:
                    context.progress.report(
                        processed,
                        total_work,
                        f"analysed {processed} sequence frames",
                    )
            stats.flush()
            by_session[source.id] = stats
            context.progress.report(
                processed,
                total_work,
                f"analysed sequences in session {source.name}",
            )
        return tuple(
            by_session[session_id]
            for session_id in context.comparison.session_ids
        )

    def _build_payload(
        self,
        context: AnalysisContext,
        analysis_input: Any,
        comparison: ComparisonContext,
        ordered: tuple[_SessionSequenceStats, ...],
        store: _SequenceStore,
        parameters: dict[str, Any],
    ) -> tuple[
        dict[str, Any],
        tuple[ArtifactSource, ...],
        dict[str, Any],
    ]:
        baseline_id = (
            comparison.base_session_id or comparison.session_ids[0]
        )
        totals = {
            (session.source.id, mode, length): session.occurrence_total(
                mode,
                length,
            )
            for session in ordered
            for mode in _SEQUENCE_MODES
            for length in _SEQUENCE_LENGTHS
        }
        sessions = [
            _session_summary(
                session,
                store,
                baseline_id,
            )
            for session in ordered
        ]
        matrix, ranked, notable_count = _sequence_matrix(
            store,
            ordered,
            baseline_id,
            totals,
            parameters,
        )
        union_count = store.union_unique_count()
        payload = {
            "schema": "crt.message_sequence_differences",
            "schema_version": MESSAGE_SEQUENCE_ARTIFACT_SCHEMA_VERSION,
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
                "parameters": parameters,
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
                "union_sequence_count": union_count,
                "notable_change_count": notable_count,
                "returned_notable_change_count": len(ranked),
                "notable_changes_truncated": notable_count > len(ranked),
                "matrix_complete": True,
                "sequence_lengths": list(_SEQUENCE_LENGTHS),
                "sequence_modes": list(_SEQUENCE_MODES),
            },
            "storage": {
                "mode": "bounded_memory_sqlite_exact",
                "memory_sequence_threshold": parameters[
                    "memory_sequence_threshold"
                ],
                "sequence_tracking_complete": True,
                "untracked_sequence_count": 0,
                "temporary_store_scope": "analysis_run",
            },
            "sessions": sessions,
            "sequences": matrix,
            "ranked_changes": ranked,
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
                        else "compared"
                    ),
                    "frame_count": session.observed_frame_count,
                    "sha256": session.source.sha256,
                },
            )
            for session in ordered
        )
        metadata = {
            "comparison_set_id": comparison.id,
            "baseline_session_id": baseline_id,
            "session_count": len(ordered),
            "sequence_count": union_count,
            "notable_change_count": notable_count,
        }
        return payload, artifact_sources, metadata


def _session_summary(
    session: _SessionSequenceStats,
    store: _SequenceStore,
    baseline_id: str,
) -> dict[str, Any]:
    unique = store.unique_counts(session.source.id)
    is_base = session.source.id == baseline_id
    new_count, missing_count = (
        (0, 0)
        if is_base
        else store.new_missing_counts(session.source.id, baseline_id)
    )
    return {
        "id": session.source.id,
        "name": session.source.name,
        "source": session.source.source,
        "status": session.source.status,
        "role": "base" if is_base else "compared",
        "declared_frame_count": session.source.frame_count,
        "reader_frame_count": session.source.frames.frame_count,
        "observed_frame_count": session.observed_frame_count,
        "skipped_non_data_frame_count": (
            session.skipped_non_data_frame_count
        ),
        "raw_event_count": session.raw_event_count,
        "collapsed_event_count": session.collapsed_event_count,
        "raw_pair_occurrence_count": session.occurrence_total("raw", 2),
        "raw_triple_occurrence_count": session.occurrence_total("raw", 3),
        "collapsed_pair_occurrence_count": session.occurrence_total(
            "collapsed",
            2,
        ),
        "collapsed_triple_occurrence_count": session.occurrence_total(
            "collapsed",
            3,
        ),
        "raw_pair_unique_count": unique.get(("raw", 2), 0),
        "raw_triple_unique_count": unique.get(("raw", 3), 0),
        "collapsed_pair_unique_count": unique.get(("collapsed", 2), 0),
        "collapsed_triple_unique_count": unique.get(("collapsed", 3), 0),
        "new_sequence_count": new_count,
        "missing_sequence_count": missing_count,
        "unique_cycle_sequence_count": store.unique_cycle_count(
            session.source.id
        ),
        "buffer_flush_count": session.flush_count,
        "sha256": session.source.sha256,
    }


def _sequence_matrix(
    store: _SequenceStore,
    sessions: tuple[_SessionSequenceStats, ...],
    baseline_id: str,
    totals: dict[tuple[str, str, int], int],
    parameters: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    session_order = {
        session.source.id: index for index, session in enumerate(sessions)
    }
    matrix: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []

    current_group: tuple[str, int, str] | None = None
    current_cycle = False
    current_self = False
    metrics_by_session: dict[str, dict[str, Any]] = {}

    def flush_group() -> None:
        nonlocal current_group
        if current_group is None:
            return
        mode, length, encoded = current_group
        items = _decode_sequence(encoded)
        baseline = metrics_by_session.get(baseline_id)
        rows: list[dict[str, Any]] = []
        for session in sessions:
            session_id = session.source.id
            current = metrics_by_session.get(session_id)
            change = _sequence_change(
                baseline,
                current,
                parameters,
            )
            rows.append(
                {
                    "session_id": session_id,
                    "session_name": session.source.name,
                    "role": (
                        "base" if session_id == baseline_id else "compared"
                    ),
                    "present": current is not None,
                    "statistics": current,
                    "change": change,
                }
            )
            if session_id != baseline_id and change["reasons"]:
                changes.append(
                    {
                        "session_id": session_id,
                        "session_name": session.source.name,
                        "mode": mode,
                        "sequence_length": length,
                        "sequence_key": encoded,
                        "sequence_text": _sequence_text(items),
                        "sequence": [
                            _message_key_payload(item) for item in items
                        ],
                        "is_cycle": current_cycle,
                        "is_self_transition": current_self,
                        "reasons": list(change["reasons"]),
                        "baseline": baseline,
                        "current": current,
                        "occurrence_delta_percent": change[
                            "occurrence_delta_percent"
                        ],
                        "share_delta_percentage_points": change[
                            "share_delta_percentage_points"
                        ],
                        "mean_span_delta_percent": change[
                            "mean_span_delta_percent"
                        ],
                    }
                )
        matrix.append(
            {
                "mode": mode,
                "sequence_length": length,
                "sequence_key": encoded,
                "sequence_text": _sequence_text(items),
                "sequence": [
                    _message_key_payload(item) for item in items
                ],
                "is_cycle": current_cycle,
                "is_self_transition": current_self,
                "baseline": baseline,
                "sessions": rows,
            }
        )

    for row in store.grouped_rows():
        (
            mode,
            length,
            encoded,
            is_cycle,
            is_self_transition,
            session_id,
            count,
            first_start_row,
            last_start_row,
            first_timestamp_ns,
            last_timestamp_ns,
            min_span_ns,
            max_span_ns,
            span_sum_ns,
        ) = row
        group = (str(mode), int(length), str(encoded))
        if current_group != group:
            flush_group()
            current_group = group
            current_cycle = bool(is_cycle)
            current_self = bool(is_self_transition)
            metrics_by_session = {}
        total = totals.get((str(session_id), str(mode), int(length)), 0)
        metrics_by_session[str(session_id)] = _metrics_payload(
            count=int(count),
            total=total,
            first_start_row=int(first_start_row),
            last_start_row=int(last_start_row),
            first_timestamp_ns=int(first_timestamp_ns),
            last_timestamp_ns=int(last_timestamp_ns),
            min_span_ns=int(min_span_ns),
            max_span_ns=int(max_span_ns),
            span_sum_ns=int(span_sum_ns),
        )
    flush_group()

    changes.sort(
        key=lambda item: (
            session_order[str(item["session_id"])],
            _reason_priority(item["reasons"]),
            -_change_magnitude(item),
            0 if item["mode"] == "raw" else 1,
            int(item["sequence_length"]),
            str(item["sequence_key"]),
        )
    )
    notable_count = len(changes)
    maximum = parameters["maximum_ranked_changes"]
    return matrix, changes[:maximum], notable_count


def _metrics_payload(
    *,
    count: int,
    total: int,
    first_start_row: int,
    last_start_row: int,
    first_timestamp_ns: int,
    last_timestamp_ns: int,
    min_span_ns: int,
    max_span_ns: int,
    span_sum_ns: int,
) -> dict[str, Any]:
    return {
        "occurrence_count": count,
        "share_percent": _round(0.0 if not total else count * 100 / total),
        "first_start_row": first_start_row,
        "last_start_row": last_start_row,
        "first_timestamp_ns": first_timestamp_ns,
        "last_timestamp_ns": last_timestamp_ns,
        "min_span_ns": min_span_ns,
        "mean_span_ns": _round(span_sum_ns / count),
        "max_span_ns": max_span_ns,
    }


def _sequence_change(
    baseline: dict[str, Any] | None,
    current: dict[str, Any] | None,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    reasons: list[str] = []
    occurrence_delta_percent: float | None = None
    share_delta: float | None = None
    mean_span_delta_percent: float | None = None

    if baseline is None and current is not None:
        reasons.append("new_sequence")
    elif baseline is not None and current is None:
        reasons.append("missing_sequence")
    elif baseline is not None and current is not None:
        baseline_count = int(baseline["occurrence_count"])
        current_count = int(current["occurrence_count"])
        if baseline_count:
            occurrence_delta_percent = _round(
                (current_count - baseline_count) * 100 / baseline_count
            )
            if (
                abs(occurrence_delta_percent)
                >= parameters["occurrence_change_threshold_percent"]
            ):
                reasons.append(
                    "occurrence_increase"
                    if occurrence_delta_percent > 0
                    else "occurrence_decrease"
                )

        share_delta = _round(
            float(current["share_percent"])
            - float(baseline["share_percent"])
        )
        if (
            abs(share_delta)
            >= parameters["share_change_threshold_percentage_points"]
        ):
            reasons.append(
                "share_increase"
                if share_delta > 0
                else "share_decrease"
            )

        baseline_span = float(baseline["mean_span_ns"])
        current_span = float(current["mean_span_ns"])
        if baseline_span:
            mean_span_delta_percent = _round(
                (current_span - baseline_span) * 100 / abs(baseline_span)
            )
            if (
                abs(mean_span_delta_percent)
                >= parameters["mean_span_change_threshold_percent"]
            ):
                reasons.append(
                    "mean_span_increase"
                    if mean_span_delta_percent > 0
                    else "mean_span_decrease"
                )

    return {
        "reasons": reasons,
        "occurrence_delta_percent": occurrence_delta_percent,
        "share_delta_percentage_points": share_delta,
        "mean_span_delta_percent": mean_span_delta_percent,
    }


def _comparison_input(
    context: AnalysisContext,
) -> tuple[Any, ComparisonContext]:
    if len(context.inputs) != 1 or context.inputs[0].kind != "comparison_set":
        raise ValueError(
            "message sequence comparison requires exactly one "
            "comparison_set input"
        )
    comparison = context.comparison
    if comparison is None:
        raise ValueError(
            "message sequence comparison requires comparison context"
        )
    if comparison.id != context.inputs[0].source_id:
        raise ValueError(
            "message sequence comparison context does not match input"
        )
    return context.inputs[0], comparison


def _parameters(value: Any) -> dict[str, Any]:
    payload = dict(value or {})
    return {
        "occurrence_change_threshold_percent": _number_parameter(
            payload,
            "occurrence_change_threshold_percent",
            _DEFAULT_OCCURRENCE_THRESHOLD_PERCENT,
        ),
        "share_change_threshold_percentage_points": _number_parameter(
            payload,
            "share_change_threshold_percentage_points",
            _DEFAULT_SHARE_THRESHOLD_PERCENTAGE_POINTS,
        ),
        "mean_span_change_threshold_percent": _number_parameter(
            payload,
            "mean_span_change_threshold_percent",
            _DEFAULT_MEAN_SPAN_THRESHOLD_PERCENT,
        ),
        "maximum_ranked_changes": _integer_parameter(
            payload,
            "maximum_ranked_changes",
            _DEFAULT_MAXIMUM_RANKED_CHANGES,
            _MAXIMUM_RANKED_CHANGES_LIMIT,
        ),
        "memory_sequence_threshold": _integer_parameter(
            payload,
            "memory_sequence_threshold",
            _DEFAULT_MEMORY_SEQUENCE_THRESHOLD,
            _MAXIMUM_MEMORY_SEQUENCE_THRESHOLD,
        ),
        "include_non_data_frames": _boolean_parameter(
            payload,
            "include_non_data_frames",
            False,
        ),
    }


def _number_parameter(
    payload: dict[str, Any],
    key: str,
    default: float,
) -> float:
    value = payload.get(key, default)
    if isinstance(value, bool):
        raise ValueError(f"{key} must be a finite non-negative number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{key} must be a finite non-negative number"
        ) from exc
    if not isfinite(number) or number < 0:
        raise ValueError(f"{key} must be a finite non-negative number")
    return _round(number)


def _integer_parameter(
    payload: dict[str, Any],
    key: str,
    default: int,
    maximum: int,
) -> int:
    value = payload.get(key, default)
    message = f"{key} must be an integer between 1 and {maximum}"
    if isinstance(value, bool):
        raise ValueError(message)
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(message) from exc
    if isinstance(value, float) and (
        not isfinite(value) or not value.is_integer()
    ):
        raise ValueError(message)
    if isinstance(value, str) and str(number) != value.strip():
        raise ValueError(message)
    if not 1 <= number <= maximum:
        raise ValueError(message)
    return number


def _boolean_parameter(
    payload: dict[str, Any],
    key: str,
    default: bool,
) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _message_key(frame: CanFrame) -> MessageKey:
    return (
        frame.channel,
        frame.arbitration_id,
        frame.is_extended_id,
        frame.is_remote_frame,
        frame.is_error_frame,
    )


def _message_key_payload(key: MessageKey) -> dict[str, Any]:
    channel, arbitration_id, extended, remote, error = key
    width = 8 if extended else 3
    kind = "error" if error else "remote" if remote else "data"
    return {
        "message_key": _message_key_text(key),
        "channel": channel,
        "arbitration_id": arbitration_id,
        "arbitration_id_hex": f"{arbitration_id:0{width}X}",
        "is_extended_id": extended,
        "frame_kind": kind,
        "is_remote_frame": remote,
        "is_error_frame": error,
    }


def _message_key_text(key: MessageKey) -> str:
    channel, arbitration_id, extended, remote, error = key
    width = 8 if extended else 3
    kind = "error" if error else "remote" if remote else "data"
    return (
        f"{channel}:{'EXT' if extended else 'STD'}:"
        f"{arbitration_id:0{width}X}:{kind}"
    )


def _encode_sequence(items: tuple[MessageKey, ...]) -> str:
    return ";".join(
        ",".join(
            (
                str(channel),
                str(arbitration_id),
                "1" if extended else "0",
                "1" if remote else "0",
                "1" if error else "0",
            )
        )
        for channel, arbitration_id, extended, remote, error in items
    )


def _decode_sequence(value: str) -> tuple[MessageKey, ...]:
    if not value:
        return ()
    result: list[MessageKey] = []
    for token in value.split(";"):
        channel, arbitration_id, extended, remote, error = token.split(",")
        result.append(
            (
                int(channel),
                int(arbitration_id),
                extended == "1",
                remote == "1",
                error == "1",
            )
        )
    return tuple(result)


def _sequence_text(items: tuple[MessageKey, ...]) -> str:
    return " → ".join(_message_key_text(item) for item in items)


def _reason_priority(reasons: Any) -> int:
    priority = {
        "missing_sequence": 0,
        "new_sequence": 1,
        "occurrence_decrease": 2,
        "occurrence_increase": 3,
        "share_decrease": 4,
        "share_increase": 5,
        "mean_span_increase": 6,
        "mean_span_decrease": 7,
    }
    return min(
        (priority.get(str(reason), 99) for reason in reasons),
        default=99,
    )


def _change_magnitude(item: dict[str, Any]) -> float:
    values = (
        item.get("occurrence_delta_percent"),
        item.get("share_delta_percentage_points"),
        item.get("mean_span_delta_percent"),
    )
    return max(
        (
            abs(float(value))
            for value in values
            if value is not None
        ),
        default=0.0,
    )


def _round(value: float) -> float:
    return round(float(value), 6)


__all__ = [
    "MESSAGE_SEQUENCE_ALGORITHM_VERSION",
    "MESSAGE_SEQUENCE_ARTIFACT_SCHEMA_VERSION",
    "MESSAGE_SEQUENCE_PROVIDER_ID",
    "MESSAGE_SEQUENCE_PROVIDER_VERSION",
    "MessageSequenceComparisonProvider",
]
