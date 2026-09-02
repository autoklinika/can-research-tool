from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
)

from app.signal_hypothesis_review_service import SignalHypothesisReviewService
from .signal_hypothesis_view_stage1 import SignalHypothesisView as _Stage1SignalHypothesisView


class SignalHypothesisView(_Stage1SignalHypothesisView):
    """Stage 1 AI hypothesis view plus append-only Stage 2 operator review."""

    def __init__(self, project, comparison_set, parent=None) -> None:
        self.review_service = SignalHypothesisReviewService(project)
        super().__init__(project, comparison_set, parent)

    def _build_ui(self) -> None:
        super()._build_ui()
        root = self.layout()

        heading = QLabel(
            "Decyzja operatora — append-only. Potwierdzenie, odrzucenie lub edycja nie zmienia "
            "oryginalnej hipotezy AI; zapisuje osobny artefakt audytowy.",
            self,
        )
        heading.setObjectName("signalHypothesisReviewHeading")
        heading.setWordWrap(True)
        root.addWidget(heading)

        self.review_status_label = QLabel("Decyzja operatora: brak.", self)
        self.review_status_label.setObjectName("signalHypothesisReviewStatus")
        self.review_status_label.setWordWrap(True)
        root.addWidget(self.review_status_label)

        form = QFormLayout()
        self.review_name_edit = QLineEdit(self)
        self.review_name_edit.setObjectName("signalHypothesisReviewName")
        self.review_name_edit.setMaxLength(120)
        form.addRow("Nazwa po weryfikacji:", self.review_name_edit)

        self.review_meaning_edit = QPlainTextEdit(self)
        self.review_meaning_edit.setObjectName("signalHypothesisReviewMeaning")
        self.review_meaning_edit.setMaximumHeight(72)
        form.addRow("Znaczenie / opis operatora:", self.review_meaning_edit)

        numeric_row = QHBoxLayout()
        self.review_unit_edit = QLineEdit(self)
        self.review_unit_edit.setObjectName("signalHypothesisReviewUnit")
        self.review_unit_edit.setPlaceholderText("jednostka lub puste")
        self.review_unit_edit.setMaxLength(60)
        numeric_row.addWidget(QLabel("unit:", self))
        numeric_row.addWidget(self.review_unit_edit)
        self.review_scale_edit = QLineEdit(self)
        self.review_scale_edit.setObjectName("signalHypothesisReviewScale")
        self.review_scale_edit.setPlaceholderText("scale lub puste")
        numeric_row.addWidget(QLabel("scale:", self))
        numeric_row.addWidget(self.review_scale_edit)
        self.review_offset_edit = QLineEdit(self)
        self.review_offset_edit.setObjectName("signalHypothesisReviewOffset")
        self.review_offset_edit.setPlaceholderText("offset lub puste")
        numeric_row.addWidget(QLabel("offset:", self))
        numeric_row.addWidget(self.review_offset_edit)
        form.addRow("Parametry:", numeric_row)

        self.review_rationale_edit = QPlainTextEdit(self)
        self.review_rationale_edit.setObjectName("signalHypothesisReviewRationale")
        self.review_rationale_edit.setMaximumHeight(86)
        form.addRow("Uzasadnienie operatora:", self.review_rationale_edit)

        self.review_note_edit = QLineEdit(self)
        self.review_note_edit.setObjectName("signalHypothesisReviewNote")
        self.review_note_edit.setMaxLength(1000)
        self.review_note_edit.setPlaceholderText(
            "notatka audytowa; przy odrzuceniu wymagany jest powód"
        )
        form.addRow("Notatka decyzji:", self.review_note_edit)
        root.addLayout(form)

        actions = QHBoxLayout()
        self.review_edit_button = QPushButton("Zapisz edycję", self)
        self.review_edit_button.setObjectName("signalHypothesisReviewEdit")
        self.review_edit_button.clicked.connect(
            lambda _checked=False: self._submit_review("edit")
        )
        actions.addWidget(self.review_edit_button)

        self.review_verify_button = QPushButton("Potwierdź", self)
        self.review_verify_button.setObjectName("signalHypothesisReviewVerify")
        self.review_verify_button.clicked.connect(
            lambda _checked=False: self._submit_review("verify")
        )
        actions.addWidget(self.review_verify_button)

        self.review_reject_button = QPushButton("Odrzuć", self)
        self.review_reject_button.setObjectName("signalHypothesisReviewReject")
        self.review_reject_button.clicked.connect(
            lambda _checked=False: self._submit_review("reject")
        )
        actions.addWidget(self.review_reject_button)

        self.review_refresh_button = QPushButton("Odśwież decyzję", self)
        self.review_refresh_button.setObjectName("signalHypothesisReviewRefresh")
        self.review_refresh_button.clicked.connect(self._load_review_for_current_source)
        actions.addWidget(self.review_refresh_button)
        actions.addStretch(1)
        root.addLayout(actions)
        self._refresh_review_actions()

    @Slot()
    @Slot(int)
    def _show_selected_hypothesis(self, _index: int = -1) -> None:
        super()._show_selected_hypothesis(_index)
        self._load_review_for_current_source()

    def _set_running(self, running: bool) -> None:
        super()._set_running(running)
        self._refresh_review_actions()

    @Slot()
    def _load_review_for_current_source(self) -> None:
        artifact_id = self._current_hypothesis_artifact_id()
        if not artifact_id:
            self._clear_review_editor()
            self.review_status_label.setText("Decyzja operatora: brak hipotezy do oceny.")
            self._refresh_review_actions()
            return

        artifact = next(
            (
                item
                for item in self.catalog.list_hypothesis_artifacts(self.comparison_set_id)
                if item.id == artifact_id
            ),
            None,
        )
        if artifact is None:
            self._clear_review_editor()
            self.review_status_label.setText("Decyzja operatora: nie znaleziono hipotezy źródłowej.")
            self._refresh_review_actions()
            return

        try:
            source_payload = self.catalog.read_hypothesis(artifact)
            source_hypothesis = _mapping(source_payload.get("hypothesis"))
            reviews = self.review_service.list_review_artifacts(
                self.comparison_set_id,
                hypothesis_artifact_id=artifact_id,
            )
            latest_payload = (
                self.review_service.read_review(reviews[0]) if reviews else None
            )
        except Exception as exc:
            self.review_status_label.setText(f"Nie można odczytać decyzji operatora: {exc}")
            self._refresh_review_actions()
            return

        effective = source_hypothesis
        if latest_payload is not None:
            effective = _mapping(latest_payload.get("effective_hypothesis")) or source_hypothesis
        self._populate_review_editor(effective)

        if latest_payload is None:
            status_text = "brak — hipoteza nadal tylko suggested / verified=false"
            note = ""
            edited_fields: list[str] = []
        else:
            review = _mapping(latest_payload.get("review"))
            status = str(review.get("status", ""))
            status_text = {
                "verified": "POTWIERDZONA",
                "rejected": "ODRZUCONA",
                "edited": "EDYCJA ZAPISANA — jeszcze niepotwierdzona",
            }.get(status, status or "nieznana")
            note = str(review.get("operator_note", "") or "")
            fields_value = review.get("edited_fields")
            edited_fields = (
                [str(item) for item in fields_value]
                if isinstance(fields_value, list)
                else []
            )

        suffix = f" | historia: {len(reviews)} decyzji"
        if edited_fields:
            suffix += " | zmieniono: " + ", ".join(edited_fields)
        if note:
            suffix += f" | notatka: {note}"
        self.review_status_label.setText(f"Decyzja operatora: {status_text}{suffix}")
        self.guardrail_label.setText(
            "Kontrakt: źródłowa hipoteza AI pozostaje suggested / verified=false i jest niezmienna. "
            f"Aktualna decyzja operatora: {status_text}."
        )
        self._refresh_review_actions()

    def _populate_review_editor(self, hypothesis: Mapping[str, Any]) -> None:
        self.review_name_edit.setText(str(hypothesis.get("name", "") or ""))
        self.review_meaning_edit.setPlainText(
            str(hypothesis.get("physical_meaning", "") or "")
        )
        self.review_unit_edit.setText(str(hypothesis.get("unit", "") or ""))
        scale = hypothesis.get("scale")
        offset = hypothesis.get("offset")
        self.review_scale_edit.setText("" if scale is None else str(scale))
        self.review_offset_edit.setText("" if offset is None else str(offset))
        self.review_rationale_edit.setPlainText(
            str(hypothesis.get("rationale", "") or "")
        )

    def _clear_review_editor(self) -> None:
        self.review_name_edit.clear()
        self.review_meaning_edit.clear()
        self.review_unit_edit.clear()
        self.review_scale_edit.clear()
        self.review_offset_edit.clear()
        self.review_rationale_edit.clear()
        self.review_note_edit.clear()

    def _operator_hypothesis(self) -> dict[str, object]:
        return {
            "name": self.review_name_edit.text().strip(),
            "physical_meaning": self.review_meaning_edit.toPlainText().strip(),
            "unit": self.review_unit_edit.text().strip() or None,
            "scale": self.review_scale_edit.text().strip() or None,
            "offset": self.review_offset_edit.text().strip() or None,
            "rationale": self.review_rationale_edit.toPlainText().strip(),
        }

    @Slot(str)
    def _submit_review(self, action: str) -> None:
        artifact_id = self._current_hypothesis_artifact_id()
        if not artifact_id:
            self.review_status_label.setText("Brak wybranej hipotezy do oceny.")
            return
        note = self.review_note_edit.text().strip()
        if action == "reject" and not note:
            self.review_status_label.setText(
                "Odrzucenie wymaga krótkiego powodu w polu Notatka decyzji."
            )
            return
        try:
            result = self.review_service.run(
                self.comparison_set_id,
                hypothesis_artifact_id=artifact_id,
                action=action,
                operator_hypothesis=(
                    None if action == "reject" else self._operator_hypothesis()
                ),
                operator_note=note,
            )
        except Exception as exc:
            self.review_status_label.setText(f"Decyzja nie została zapisana: {exc}")
            return

        if not result.artifacts:
            self.review_status_label.setText("Provider review nie zwrócił artefaktu.")
            return
        self.review_note_edit.clear()
        labels = {
            "verify": "potwierdzono hipotezę",
            "reject": "odrzucono hipotezę",
            "edit": "zapisano edycję hipotezy",
        }
        self.output_message.emit(f"Signal Hypothesis Review: {labels[action]}")
        self.status_label.setText(
            f"Decyzja operatora zapisana append-only: {labels[action]}. Źródłowa hipoteza AI nie została zmieniona."
        )
        self._load_review_for_current_source()

    def _current_hypothesis_artifact_id(self) -> str:
        if not hasattr(self, "hypothesis_combo"):
            return ""
        return str(self.hypothesis_combo.currentData() or "")

    def _refresh_review_actions(self) -> None:
        ready = (
            hasattr(self, "review_verify_button")
            and getattr(self, "_task", None) is None
            and bool(self._current_hypothesis_artifact_id())
        )
        if not hasattr(self, "review_verify_button"):
            return
        self.review_verify_button.setEnabled(ready)
        self.review_reject_button.setEnabled(ready)
        self.review_edit_button.setEnabled(ready)
        self.review_refresh_button.setEnabled(ready)
        self.review_name_edit.setEnabled(ready)
        self.review_meaning_edit.setEnabled(ready)
        self.review_unit_edit.setEnabled(ready)
        self.review_scale_edit.setEnabled(ready)
        self.review_offset_edit.setEnabled(ready)
        self.review_rationale_edit.setEnabled(ready)
        self.review_note_edit.setEnabled(ready)


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


__all__ = ["SignalHypothesisView"]
