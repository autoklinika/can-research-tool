from __future__ import annotations

from PySide6.QtCore import Slot

from .comparison_analysis_dialog import (
    ComparisonAnalysisDialog,
    _configure_table,
    _dict_list,
    _number,
    _role,
    _session_name,
    _set_row,
)


_SEQUENCE_REASON_LABELS = {
    "new_sequence": "Nowa sekwencja",
    "missing_sequence": "Brakująca sekwencja",
    "occurrence_increase": "Liczba wystąpień ↑",
    "occurrence_decrease": "Liczba wystąpień ↓",
    "share_increase": "Udział ↑",
    "share_decrease": "Udział ↓",
    "mean_span_increase": "Czas sekwencji ↑",
    "mean_span_decrease": "Czas sekwencji ↓",
}
_SEQUENCE_SESSION_HEADERS = (
    "Sesja",
    "Rola",
    "Ramki",
    "Pary raw",
    "Trójki raw",
    "Pary zwinięte",
    "Trójki zwinięte",
    "Nowe",
    "Brakujące",
    "Cykle",
)
_SEQUENCE_CHANGE_HEADERS = (
    "Sesja",
    "Tryb",
    "Długość",
    "Sekwencja",
    "Zmiana",
    "Baza: liczba",
    "Bieżąca: liczba",
    "Δ liczby [%]",
    "Baza: udział [%]",
    "Bieżący: udział [%]",
    "Baza: czas [ms]",
    "Bieżący: czas [ms]",
)


class MessageSequenceComparisonAnalysisDialog(ComparisonAnalysisDialog):
    """Comparison dialog extended with the Stage 3 sequence artifact."""

    @Slot()
    @Slot(int)
    def _show_selected_artifact(self, index: int = -1) -> None:
        super()._show_selected_artifact(index)
        artifact_id = str(self.artifact_combo.currentData() or "")
        artifact = next(
            (item for item in self._artifacts if item.id == artifact_id),
            None,
        )
        if artifact is None:
            return
        try:
            payload = self.service.artifacts.read_json(artifact)
        except Exception:
            return
        if payload.get("schema") == "crt.message_sequence_differences":
            self._render_message_sequences(payload)

    def _render_message_sequences(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        _configure_table(
            self.sessions_table,
            _SEQUENCE_SESSION_HEADERS,
        )
        _configure_table(
            self.changes_table,
            _SEQUENCE_CHANGE_HEADERS,
        )
        summary = (
            payload.get("summary")
            if isinstance(payload.get("summary"), dict)
            else {}
        )
        comparison = (
            payload.get("comparison_set")
            if isinstance(payload.get("comparison_set"), dict)
            else {}
        )
        sessions = _dict_list(payload.get("sessions"))
        changes = _dict_list(payload.get("ranked_changes"))
        base_id = str(summary.get("baseline_session_id") or "")
        base_name = _session_name(sessions, base_id)
        self.summary_label.setText(
            f"Baza: {base_name or '—'}. "
            f"Sesje: {summary.get('session_count', '—')}. "
            f"Unikalne sekwencje: "
            f"{summary.get('union_sequence_count', '—')}. "
            f"Zmiany: {summary.get('notable_change_count', '—')}. "
            f"Macierz kompletna: "
            f"{'tak' if summary.get('matrix_complete') else 'nie'}. "
            f"Synchronizacja: "
            f"{comparison.get('synchronization_mode', '—')}."
        )
        self.sessions_table.setRowCount(len(sessions))
        for row, item in enumerate(sessions):
            _set_row(
                self.sessions_table,
                row,
                (
                    item.get("name", "—"),
                    _role(item),
                    item.get("observed_frame_count", "—"),
                    item.get("raw_pair_unique_count", "—"),
                    item.get("raw_triple_unique_count", "—"),
                    item.get("collapsed_pair_unique_count", "—"),
                    item.get("collapsed_triple_unique_count", "—"),
                    item.get("new_sequence_count", "—"),
                    item.get("missing_sequence_count", "—"),
                    item.get("unique_cycle_sequence_count", "—"),
                ),
            )

        self.changes_table.setRowCount(len(changes))
        for row, item in enumerate(changes):
            baseline = (
                item.get("baseline")
                if isinstance(item.get("baseline"), dict)
                else {}
            )
            current = (
                item.get("current")
                if isinstance(item.get("current"), dict)
                else {}
            )
            reasons = (
                item.get("reasons")
                if isinstance(item.get("reasons"), list)
                else []
            )
            sequence_text = str(item.get("sequence_text") or "—")
            if item.get("is_cycle"):
                sequence_text = f"[CYKL] {sequence_text}"
            elif item.get("is_self_transition"):
                sequence_text = f"[POWTÓRZENIE] {sequence_text}"
            _set_row(
                self.changes_table,
                row,
                (
                    item.get("session_name", "—"),
                    _mode_label(item.get("mode")),
                    item.get("sequence_length", "—"),
                    sequence_text,
                    ", ".join(
                        _SEQUENCE_REASON_LABELS.get(
                            str(reason),
                            str(reason),
                        )
                        for reason in reasons
                    ),
                    baseline.get("occurrence_count", "—"),
                    current.get("occurrence_count", "—"),
                    _number(item.get("occurrence_delta_percent")),
                    _number(baseline.get("share_percent")),
                    _number(current.get("share_percent")),
                    _milliseconds(baseline.get("mean_span_ns")),
                    _milliseconds(current.get("mean_span_ns")),
                ),
            )


def _mode_label(value: object) -> str:
    return "Surowa" if value == "raw" else "Po zwinięciu"


def _milliseconds(value: object) -> object:
    if value is None:
        return "—"
    try:
        return round(float(value) / 1_000_000.0, 6)
    except (TypeError, ValueError):
        return "—"


__all__ = ["MessageSequenceComparisonAnalysisDialog"]
