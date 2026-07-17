from __future__ import annotations

import ast
from pathlib import Path

from app.live_capture_controller import (
    CaptureMode,
    LiveCaptureController,
    StartCaptureRequest,
)
from app.markers import MarkerPreset
from kvaser.backend import KvaserChannelInfo, KvaserReceiveMode


class RecordingCaptureService:
    def __init__(self, *, channel_provider) -> None:
        self.channel_provider = channel_provider
        self.started_with = None
        self.stop_calls = 0
        self.wait_calls: list[float | None] = []
        self.status_result = object()
        self.frames_result = object()
        self.messages_result = object()
        self.marker_result = object()
        self.is_active = False

    def start(self, config):
        self.started_with = config
        self.is_active = True
        return None

    def stop(self) -> None:
        self.stop_calls += 1
        self.is_active = False

    def wait(self, timeout: float | None = None) -> bool:
        self.wait_calls.append(timeout)
        return True

    def status(self):
        return self.status_result

    def live_snapshot_since(self, after_sequence: int | None):
        assert after_sequence == 41
        return self.frames_result

    def live_messages_snapshot_since(self, after_sequence: int | None):
        assert after_sequence == 17
        return self.messages_result

    def add_marker(self, preset, *, source: str, note: str):
        assert preset.name == "EGR"
        assert source == "button"
        assert note == "test"
        return self.marker_result


def _channels() -> list[KvaserChannelInfo]:
    return [
        KvaserChannelInfo(
            number=0,
            name="Kvaser Leaf Light",
            serial_number="123",
            product_number="73-30130-00685-0",
            supports_silent_mode=True,
        ),
        KvaserChannelInfo(
            number=2,
            name="Kvaser Virtual CAN Driver",
            serial_number="",
            product_number="",
            supports_silent_mode=False,
        ),
    ]


def _controller() -> tuple[LiveCaptureController, RecordingCaptureService]:
    created: list[RecordingCaptureService] = []

    def service_factory(*, channel_provider):
        service = RecordingCaptureService(channel_provider=channel_provider)
        created.append(service)
        return service

    controller = LiveCaptureController(
        service_factory=service_factory,
        channel_provider=_channels,
    )
    assert len(created) == 1
    assert created[0].channel_provider is _channels
    return controller, created[0]


def test_controller_creates_service_and_exposes_neutral_adapters() -> None:
    controller, _service = _controller()

    adapters = controller.list_adapters()

    assert [(adapter.number, adapter.name) for adapter in adapters] == [
        (0, "Kvaser Leaf Light"),
        (2, "Kvaser Virtual CAN Driver"),
    ]
    assert adapters[0].is_virtual is False
    assert adapters[0].supports_silent_mode is True
    assert adapters[1].is_virtual is True


def test_start_builds_capture_config_without_exposing_it_to_the_widget(
    tmp_path: Path,
) -> None:
    controller, service = _controller()
    marker = MarkerPreset.create("EGR", "F2")

    result = controller.start(
        StartCaptureRequest(
            channel_number=2,
            bitrate=500_000,
            mode=CaptureMode.LISTEN_ONLY,
            session_name="controller-test",
            output_dir=tmp_path,
            persist_to_disk=False,
            live_buffer_capacity=250_000,
            live_message_capacity=100_000,
            marker_presets=(marker,),
        )
    )

    assert result is None
    config = service.started_with
    assert config is not None
    assert config.channel_number == 2
    assert config.bitrate == 500_000
    assert config.mode is KvaserReceiveMode.LISTEN_ONLY
    assert config.session_name == "controller-test"
    assert config.output_dir == tmp_path
    assert config.persist_to_disk is False
    assert config.live_buffer_capacity == 250_000
    assert config.live_message_capacity == 100_000
    assert config.marker_presets == (marker,)
    assert controller.is_active is True


def test_controller_maps_every_neutral_receive_mode_to_backend(tmp_path: Path) -> None:
    controller, service = _controller()

    for neutral_mode, backend_mode in (
        (CaptureMode.BENCH, KvaserReceiveMode.BENCH),
        (CaptureMode.LISTEN_ONLY, KvaserReceiveMode.LISTEN_ONLY),
    ):
        controller.start(
            StartCaptureRequest(
                channel_number=0,
                bitrate=250_000,
                mode=neutral_mode,
                session_name="mode-mapping",
                output_dir=tmp_path,
            )
        )
        assert service.started_with.mode is backend_mode


def test_controller_delegates_lifecycle_status_snapshots_and_markers() -> None:
    controller, service = _controller()
    marker = MarkerPreset.create("EGR", "F2")

    assert controller.status() is service.status_result
    assert controller.frames_since(41) is service.frames_result
    assert controller.messages_since(17) is service.messages_result
    assert controller.add_marker(marker, source="button", note="test") is service.marker_result

    controller.stop()
    assert service.stop_calls == 1
    assert controller.is_active is False
    assert controller.wait(2.5) is True
    assert service.wait_calls == [2.5]


def test_live_capture_gui_does_not_construct_service_or_config() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    for relative_path in ("gui/live_capture.py", "gui/live_save_integration.py"):
        source = (repository_root / relative_path).read_text(encoding="utf-8")
        assert "CaptureService" not in source
        assert "CaptureConfig" not in source


def test_gui_layer_does_not_import_kvaser_or_canlib() -> None:
    gui_root = Path(__file__).resolve().parents[1] / "gui"
    forbidden_imports: list[str] = []

    for path in sorted(gui_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            for module in modules:
                if module == "canlib" or module.startswith(("canlib.", "kvaser")):
                    forbidden_imports.append(f"{path.relative_to(gui_root)}: {module}")

    assert forbidden_imports == []


def test_live_capture_widget_is_not_runtime_patched() -> None:
    gui_root = Path(__file__).resolve().parents[1] / "gui"
    patched_attributes: list[str] = []

    for path in sorted(gui_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            targets = node.targets if isinstance(node, ast.Assign) else ()
            for target in targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "LiveCaptureWidget"
                ):
                    patched_attributes.append(
                        f"{path.relative_to(gui_root)}: {target.attr}"
                    )

    assert patched_attributes == []


def test_live_integrations_are_explicit_constructor_dependencies() -> None:
    source_path = Path(__file__).resolve().parents[1] / "gui" / "live_capture.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    widget_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "LiveCaptureWidget"
    )
    constructor = next(
        node
        for node in widget_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    keyword_arguments = {argument.arg for argument in constructor.args.kwonlyargs}

    assert {
        "controller",
        "filter_integration_factory",
        "save_integration_factory",
        "protocol_summary_attacher",
    } <= keyword_arguments


def test_session_view_widget_is_not_runtime_patched() -> None:
    gui_root = Path(__file__).resolve().parents[1] / "gui"
    patched_attributes: list[str] = []

    for path in sorted(gui_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            targets = node.targets if isinstance(node, ast.Assign) else ()
            for target in targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "SessionViewWidget"
                ):
                    patched_attributes.append(
                        f"{path.relative_to(gui_root)}: {target.attr}"
                    )

    assert patched_attributes == []


def test_stored_session_integrations_are_explicit_constructor_dependencies() -> None:
    source_path = Path(__file__).resolve().parents[1] / "gui" / "session_view.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    widget_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "SessionViewWidget"
    )
    constructor = next(
        node
        for node in widget_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    keyword_arguments = {argument.arg for argument in constructor.args.kwonlyargs}

    assert {
        "controller",
        "stored_integration_factory",
        "protocol_summary_attacher",
    } <= keyword_arguments
