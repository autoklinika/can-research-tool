from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any

from app.domain import Artifact

from ..contracts import AnalysisContext
from . import message_sequence as _stage3


MESSAGE_SEQUENCE_PROVIDER_ID = _stage3.MESSAGE_SEQUENCE_PROVIDER_ID
MESSAGE_SEQUENCE_PROVIDER_VERSION = _stage3.MESSAGE_SEQUENCE_PROVIDER_VERSION
MESSAGE_SEQUENCE_ALGORITHM_VERSION = _stage3.MESSAGE_SEQUENCE_ALGORITHM_VERSION
MESSAGE_SEQUENCE_ARTIFACT_SCHEMA_VERSION = (
    _stage3.MESSAGE_SEQUENCE_ARTIFACT_SCHEMA_VERSION
)


class _SourceOrderSequenceStore(_stage3._SequenceStore):
    """Exact sequence store preserving first/last timestamps by source order."""

    def upsert(
        self,
        session_id: str,
        entries: dict[_stage3.BufferedKey, _stage3._SequenceStats],
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
                first_start_row = sequence_stats.first_start_row,
                last_start_row = excluded.last_start_row,
                first_timestamp_ns = sequence_stats.first_timestamp_ns,
                last_timestamp_ns = excluded.last_timestamp_ns,
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
                    _stage3._encode_sequence(items),
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


class MessageSequenceComparisonProvider(
    _stage3.MessageSequenceComparisonProvider
):
    """Stage 3 provider with source-order exact timestamp aggregation."""

    def run(self, context: AnalysisContext) -> Artifact:
        analysis_input, comparison = _stage3._comparison_input(context)
        if comparison.synchronization_mode != "none":
            raise ValueError(
                "message sequence Stage 3 supports only "
                "synchronization_mode none"
            )
        parameters = _stage3._parameters(analysis_input.parameters)
        sources = tuple(
            context.project.session(session_id)
            for session_id in comparison.session_ids
        )
        total_work = sum(
            source.frames.frame_count for source in sources
        ) + 1
        context.progress.report(
            0,
            total_work,
            "reading immutable message sequences",
        )

        with tempfile.TemporaryDirectory(
            prefix="crt-message-sequences-"
        ) as temporary:
            store_path = Path(temporary) / "message-sequences.sqlite3"
            with _SourceOrderSequenceStore(store_path) as store:
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


__all__ = [
    "MESSAGE_SEQUENCE_ALGORITHM_VERSION",
    "MESSAGE_SEQUENCE_ARTIFACT_SCHEMA_VERSION",
    "MESSAGE_SEQUENCE_PROVIDER_ID",
    "MESSAGE_SEQUENCE_PROVIDER_VERSION",
    "MessageSequenceComparisonProvider",
]
