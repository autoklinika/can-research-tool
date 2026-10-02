from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_main_window_is_not_runtime_patched() -> None:
    gui_root = ROOT / "gui"
    patched_attributes: list[str] = []

    for path in sorted(gui_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            targets = node.targets if isinstance(node, ast.Assign) else ()
            for target in targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "MainWindow"
                ):
                    patched_attributes.append(
                        f"{path.relative_to(gui_root)}: {target.attr}"
                    )

    assert patched_attributes == []


def test_main_window_constructs_explicit_navigation_dependencies() -> None:
    source = (ROOT / "gui" / "main_window.py").read_text(encoding="utf-8")

    assert "self.navigator = services.create_project_navigator(self.tabs)" in source
    assert "self.session_management = services.create_session_management(self)" in source
    assert "self.navigator.open_session(" in source
    assert "self.navigator.close_at(index)" in source


def test_desktop_reveal_is_outside_gui_session_management() -> None:
    integration = (ROOT / "gui" / "session_management_integration.py").read_text(
        encoding="utf-8"
    )
    desktop = (ROOT / "infrastructure" / "desktop.py").read_text(encoding="utf-8")

    assert "from infrastructure.desktop import reveal_path" in integration
    assert "QDesktopServices" not in integration
    assert "QProcess" not in integration
    assert "def reveal_path(" in desktop


def test_main_window_is_not_extended_by_inheritance() -> None:
    """Window features are controllers, not subclasses stacked on MainWindow."""

    subclasses: list[str] = []
    main_window_bases: list[str] = []
    for path in sorted((ROOT / "gui").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = [ast.unparse(base) for base in node.bases]
            if node.name == "MainWindow":
                main_window_bases = bases
            elif any(base.endswith("MainWindow") and base != "QMainWindow" for base in bases):
                subclasses.append(f"{path.relative_to(ROOT)}: {node.name}({', '.join(bases)})")

    assert main_window_bases == ["QMainWindow"]
    assert subclasses == []


def test_comparison_dialog_has_a_single_specialisation() -> None:
    """Analysis tabs are composed into one dialog, not stacked as stage subclasses."""

    dialog_classes: list[str] = []
    for path in sorted((ROOT / "gui").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and any(
                ast.unparse(base).endswith("ComparisonAnalysisDialog")
                or ast.unparse(base).endswith("ComparisonVisualizationDialog")
                for base in node.bases
            ):
                dialog_classes.append(f"{path.relative_to(ROOT)}: {node.name}")

    assert dialog_classes == [
        "gui/comparison_visualization.py: ComparisonVisualizationDialog"
    ]
