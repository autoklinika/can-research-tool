from __future__ import annotations

import json
import os
import tempfile
from gc import collect
from pathlib import Path
from time import monotonic, sleep

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QSettings, QThreadPool
from PySide6.QtWidgets import QApplication

from app.comparison_sets import ComparisonSetStore
from app.experiment_diff_service import ExperimentDiffService
from app.local_ai import LocalAICompletion, LocalAIConfig
from app.marker_stream import MarkerStreamWriter, marker_path_for_session
from app.markers import CaptureMarker, MarkerPreset
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter
from app.signal_candidate_service import SignalCandidateService
from app.signal_hypothesis_service import SignalHypothesisService
from gui.comparison_visualization_stage2d1 import ComparisonVisualizationDialog
from gui.signal_hypothesis_view import SignalHypothesisView


class _FakeLocalAI:
    def __init__(self) -> None:
        self._config = LocalAIConfig(
            base_url="http://127.0.0.1:11434/v1",
            model="fake-qwen",
            timeout_s=5,
        )
        self.requests = 0
        self.content: str | None = None

    @property
    def config(self) -> LocalAIConfig:
        return self._config

    def complete(self, *, system_prompt: str, user_prompt: str, cancellation=None):
        self.requests += 1
        assert "source of truth" in system_prompt
        assert "do not return {}" in system_prompt
        supplied = json.loads(user_prompt)
        assert supplied["response_contract"]["version"] == 2
        assert supplied["candidate"]["candidate_key"] == "0:STD:123:data:B0.2"
        assert supplied["candidate"]["candidate_score"] == 1.0
        assert "raw" not in supplied
        if cancellation is not None:
            cancellation.raise_if_cancelled()
        content = self.content
        if content is None:
            content = json.dumps(
                {
                    "name": "EGR_state_candidate",
                    "physical_meaning": "Możliwy stan związany z EGR.",
                    "unit": None,
                    "scale": None,
                    "offset": None,
                    "confidence": 0.8,
                    "rationale": "Target zmienia się konsekwentnie, control pozostaje stabilny.",
                    "next_experiments": ["Powtórz stan odwrotny i sprawdź 1->0."],
                    "warnings": ["Marker nie potwierdza znaczenia fizycznego."],
                }
            )
        return LocalAICompletion(
            provider="fake-local",
            model="fake-qwen",
            endpoint="http://127.0.0.1:11434/v1/chat/completions",
            content=content,
            latency_ms=5.0,
            usage={},
        )


def main() -> int:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("Autoklinika")
    app.setApplicationName("CAN Research Tool")
    settings = QSettings()
    settings.setValue("ai/localBaseUrl", "http://127.0.0.1:11434/v1")
    settings.setValue("ai/localModel", "fake-qwen")
    settings.setValue("ai/localTimeoutSeconds", 5)
    settings.sync()

    with tempfile.TemporaryDirectory() as directory:
        project = CrtProject.create(Path(directory) / "project", name="Signal Hypothesis GUI")
        target = MarkerPreset.create("EGR disconnected", "F3")
        control = MarkerPreset.create("Control", "F4")
        first = _session(project, "first", target, control, 12, 14)
        second = _session(project, "second", target, control, 16, 18)
        comparison = ComparisonSetStore(project).create(
            name="Hypothesis correlation",
            session_ids=(first.id, second.id),
            base_session_id=first.id,
        )

        experiment = ExperimentDiffService(project)
        options = experiment.marker_options(comparison.id)
        target_option = next(item for item in options if item.preset_id == target.id)
        control_option = next(item for item in options if item.preset_id == control.id)
        experiment.run(
            comparison.id,
            target_selector=target_option.selector,
            control_selector=control_option.selector,
            pre_window_ms=30,
            post_window_ms=50,
        )
        candidate = SignalCandidateService(project).run(comparison.id).artifacts[0]
        assert candidate.artifact_type == "signal_candidates"

        fake = _FakeLocalAI()
        original_from_config = SignalHypothesisService.__dict__["from_config"]
        SignalHypothesisService.from_config = classmethod(
            lambda cls, selected_project, config: cls(selected_project, ai_client=fake)
        )
        try:
            view = SignalHypothesisView(project, comparison)
            view.show()
            _drain(app)
            assert view.candidate_artifact_combo.count() == 1
            assert view.table.rowCount() == 1
            assert view.table.item(0, 1).text() == "strong"
            assert view.table.item(0, 2).text() == "1.000"
            assert view.table.item(0, 3).text() == "123"
            assert view.table.item(0, 4).text() == "0"
            assert view.table.item(0, 5).text() == "2"
            assert view.run_button.isEnabled()
            assert fake.requests == 0

            view.run_button.click()
            assert view._task is not None
            _wait_until(app, lambda: view._task is None, timeout_s=20.0)
            assert fake.requests == 1
            assert view.progress.value() == 100
            assert view.hypothesis_combo.count() == 1
            assert "unknown_bit_state_candidate" in view.hypothesis_label.text()
            assert "verified=false" in view.hypothesis_label.text()
            assert "Powtórz eksperyment w przeciwnym stanie" in view.next_steps_label.text()

            # A syntactically valid but empty JSON object must be rejected before
            # artifact.write. The last valid hypothesis stays visible and no
            # second result is created.
            fake.content = "{}"
            view.run_button.click()
            assert view._task is not None
            _wait_until(app, lambda: view._task is None, timeout_s=20.0)
            assert fake.requests == 2
            assert view.progress.value() == 0
            assert view.hypothesis_combo.count() == 1
            assert "AI response rejected" in view.status_label.text()
            assert "response_excerpt" in view.status_label.text()
            assert "unknown_bit_state_candidate" in view.hypothesis_label.text()

            dialog = ComparisonVisualizationDialog(project, comparison.id)
            _drain(app)
            tab_names = [
                dialog.result_tabs.tabText(index)
                for index in range(dialog.result_tabs.count())
            ]
            assert "Signal Candidates" in tab_names
            assert "Signal Hypothesis" in tab_names
            assert dialog.signal_hypothesis is not None
            assert fake.requests == 2  # constructing production dialog never invokes AI

            dialog.close_for_project_change()
            dialog.close()
            view.cancel_all()
            view.close()
            _wait_until(
                app,
                lambda: QThreadPool.globalInstance().activeThreadCount() == 0,
                timeout_s=10.0,
            )
            _drain(app)
            del dialog
            del view
            collect()
        finally:
            SignalHypothesisService.from_config = original_from_config
        del project
        collect()
    return 0


def _session(
    project: CrtProject,
    name: str,
    target: MarkerPreset,
    control: MarkerPreset,
    first_delay_ms: int,
    second_delay_ms: int,
):
    path = project.live_sessions_dir / f"{name}.crt.jsonl"
    capture = CaptureSession(name=name, source="test", bitrate=250_000, channel=0)
    frames = (
        _frame(0, 90_000_000, b"\x00"),
        _frame(1, (100 + first_delay_ms) * 1_000_000, b"\x04"),
        _frame(2, 190_000_000, b"\x04"),
        _frame(3, 220_000_000, b"\x04"),
        _frame(4, 290_000_000, b"\x00"),
        _frame(5, (300 + second_delay_ms) * 1_000_000, b"\x04"),
    )
    writer = SessionStreamWriter(capture, path)
    writer.open()
    for frame in frames:
        writer.append(frame)
    writer.close({"clean_close": True, "frame_count": len(frames)})
    record = project.register_session(path, name=name, source="test", status="ready")
    project.finalize_session(path, frame_count=6, marker_count=3, duration_s=0.32)

    markers = MarkerStreamWriter(marker_path_for_session(path), presets=(target, control))
    markers.open()
    markers.append(CaptureMarker.from_preset(target, 100_000_000, source="test"))
    markers.append(CaptureMarker.from_preset(control, 200_000_000, source="test"))
    markers.append(CaptureMarker.from_preset(target, 300_000_000, source="test"))
    markers.close()
    return project.session_by_path(path) or record


def _frame(sequence: int, timestamp_ns: int, data: bytes) -> CanFrame:
    return CanFrame(
        sequence=sequence,
        timestamp_ns=timestamp_ns,
        arbitration_id=0x123,
        data=data,
        channel=0,
        is_extended_id=False,
    )


def _wait_until(app: QApplication, predicate, *, timeout_s: float) -> None:
    deadline = monotonic() + timeout_s
    while not predicate():
        if monotonic() >= deadline:
            raise AssertionError("timed out waiting for Signal Hypothesis")
        app.processEvents()
        sleep(0.01)
    QThreadPool.globalInstance().waitForDone(5_000)
    _drain(app)


def _drain(app: QApplication, cycles: int = 12) -> None:
    for _ in range(cycles):
        app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    QThreadPool.globalInstance().waitForDone(5_000)
    for _ in range(cycles):
        app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
