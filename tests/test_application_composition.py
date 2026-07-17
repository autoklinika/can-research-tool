from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_gui_has_no_install_integration_functions() -> None:
    installers: list[str] = []
    for path in sorted((ROOT / "gui").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
                "install_"
            ):
                installers.append(f"{path.relative_to(ROOT)}: {node.name}")

    assert installers == []


def test_main_uses_application_container_as_composition_root() -> None:
    source = (ROOT / "gui" / "main.py").read_text(encoding="utf-8")

    assert "container = ApplicationContainer()" in source
    assert "window = container.create_main_window()" in source
    assert "install_" not in source


def test_container_constructs_capture_and_stored_session_controllers() -> None:
    source = (ROOT / "gui" / "application_container.py").read_text(encoding="utf-8")

    assert "controller = self._live_controller_factory()" in source
    assert "LiveCaptureWidget(project, controller=controller)" in source
    assert "controller = self._stored_controller_factory(" in source
    assert "controller=controller" in source
    assert "session_widget_factory=self.create_session_view" in source


def test_dependency_graph_is_documented() -> None:
    document = ROOT / "docs" / "APPLICATION_DEPENDENCIES_PL.md"
    text = document.read_text(encoding="utf-8")

    assert "ApplicationContainer" in text
    assert "LiveCaptureController" in text
    assert "StoredSessionController" in text
    assert "ProjectNavigator" in text
