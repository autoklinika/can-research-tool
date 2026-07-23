from __future__ import annotations

from enum import Enum, auto
from inspect import Parameter, signature
from pathlib import Path
from typing import Callable

from PySide6.QtWidgets import QTabBar, QTabWidget, QWidget

from app.project import CrtProject
from app.project_dbc import active_project_dbc_paths

from .live_capture import LiveCaptureWidget
from .session_view import SessionViewWidget


class CloseTabResult(Enum):
    CLOSED = auto()
    NOT_FOUND = auto()
    ACTIVE_CAPTURE = auto()


class ProjectNavigator:
    """Own project-tab registration and saved-session view navigation."""

    def __init__(
        self,
        tabs: QTabWidget,
        *,
        session_widget_factory: Callable[..., SessionViewWidget] = SessionViewWidget,
    ) -> None:
        self.tabs = tabs
        self._session_widget_factory = session_widget_factory
        self._widgets: dict[str, QWidget] = {}

    @property
    def widgets(self) -> dict[str, QWidget]:
        return self._widgets

    def widget(self, key: str) -> QWidget | None:
        return self._widgets.get(key)

    def add_tab(
        self,
        key: str,
        widget: QWidget,
        title: str,
        *,
        closable: bool = True,
    ) -> None:
        widget.setProperty("crtTabKey", key)
        index = self.tabs.addTab(widget, title)
        self._widgets[key] = widget
        self.tabs.setCurrentIndex(index)
        if not closable:
            self.tabs.tabBar().setTabButton(
                index,
                QTabBar.ButtonPosition.RightSide,
                None,
            )

    def activate(self, key: str) -> bool:
        widget = self._widgets.get(key)
        if widget is None:
            return False
        index = self.tabs.indexOf(widget)
        if index < 0:
            self._widgets.pop(key, None)
            return False
        self.tabs.setCurrentIndex(index)
        return True

    def open_session(
        self,
        path: str | Path,
        *,
        project: CrtProject | None,
        inspector_sink: Callable[[str], None],
        output_sink: Callable[[str], None],
    ) -> SessionViewWidget:
        session_path = Path(path).resolve()
        key = self.session_key(session_path)
        existing = self._widgets.get(key)
        if isinstance(existing, SessionViewWidget) and self.activate(key):
            return existing

        dbc_paths = active_project_dbc_paths(project) if project is not None else ()
        factory_kwargs = {"dbc_paths": dbc_paths}
        if _factory_accepts_project(self._session_widget_factory):
            factory_kwargs["project"] = project
        widget = self._session_widget_factory(session_path, **factory_kwargs)
        widget.inspector_text.connect(inspector_sink)
        widget.output_message.connect(output_sink)
        self.add_tab(
            key,
            widget,
            session_path.name.removesuffix(".crt.jsonl"),
        )
        return widget

    def close_session(self, path: str | Path) -> CloseTabResult:
        widget = self._widgets.get(self.session_key(path))
        if widget is None:
            return CloseTabResult.NOT_FOUND
        return self.close_widget(widget)

    def close_at(self, index: int) -> CloseTabResult:
        widget = self.tabs.widget(index)
        if widget is None:
            return CloseTabResult.NOT_FOUND
        if isinstance(widget, LiveCaptureWidget) and widget.is_capturing:
            return CloseTabResult.ACTIVE_CAPTURE
        return self.close_widget(widget)

    def close_widget(self, widget: QWidget) -> CloseTabResult:
        index = self.tabs.indexOf(widget)
        if index < 0:
            return CloseTabResult.NOT_FOUND
        key = str(widget.property("crtTabKey") or "")
        self._shutdown_widget(widget)
        self.tabs.removeTab(index)
        if key:
            self._widgets.pop(key, None)
        widget.deleteLater()
        return CloseTabResult.CLOSED

    def close_all(self) -> None:
        for index in range(self.tabs.count() - 1, -1, -1):
            widget = self.tabs.widget(index)
            if widget is not None:
                self.close_widget(widget)

    def reload_session_dbc(self, paths: tuple[Path, ...]) -> None:
        for widget in tuple(self._widgets.values()):
            if isinstance(widget, SessionViewWidget):
                widget.reload_logical_messages(paths)

    def has_active_capture(self) -> bool:
        return any(
            isinstance(widget, LiveCaptureWidget) and widget.is_capturing
            for widget in self._widgets.values()
        )

    def shutdown_sessions(self) -> None:
        for widget in tuple(self._widgets.values()):
            if isinstance(widget, SessionViewWidget):
                widget.shutdown()

    @staticmethod
    def session_key(path: str | Path) -> str:
        return f"session:{Path(path).resolve()}"

    @staticmethod
    def _shutdown_widget(widget: QWidget) -> None:
        if isinstance(widget, (LiveCaptureWidget, SessionViewWidget)):
            widget.shutdown()


def _factory_accepts_project(factory: Callable[..., object]) -> bool:
    try:
        parameters = signature(factory).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        parameter.name == "project" or parameter.kind is Parameter.VAR_KEYWORD
        for parameter in parameters
    )
