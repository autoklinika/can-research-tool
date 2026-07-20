from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .filters import ProjectFilterRepository
from .live_filters import ActiveFilterSet
from .session_filters import FilteredSessionPage, load_filtered_session_page
from .session_stream import read_session_header


@dataclass(frozen=True, slots=True)
class StoredSessionPageState:
    path: Path
    session_title: str
    page_size: int
    generation: int
    page: FilteredSessionPage | None
    filters_enabled: bool
    available_filter_count: int
    active_filter_names: tuple[str, ...]
    filter_affects_visibility: bool
    loading: bool
    error: str = ""

    @property
    def active_filter_count(self) -> int:
        return len(self.active_filter_names)

    @property
    def page_start(self) -> int:
        return 0 if self.page is None else self.page.loaded_from_visible_index

    @property
    def last_page_start(self) -> int:
        if self.page is None or self.page.visible_frames <= 0:
            return 0
        return ((self.page.visible_frames - 1) // self.page_size) * self.page_size


class StoredSessionController:
    """Own stored-session filtering, pagination and background page loading."""

    def __init__(
        self,
        path: str | Path,
        *,
        page_size: int = 20_000,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        if page_size <= 0:
            raise ValueError("page_size must be greater than zero")
        self.path = Path(path)
        self.page_size = int(page_size)
        self._database_path = _find_project_database(self.path)
        self._available_filter_set = self._load_filter_set()
        self._available_filter_signature = self._available_filter_set.signature
        self._active_filter_set = ActiveFilterSet((), scope="stored_session")
        self._filters_enabled = False
        self._page: FilteredSessionPage | None = None
        self._page_start = 0
        self._generation = 0
        self._loading = False
        self._error = ""
        self._closed = False
        self._executor = executor or ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="crt-stored-session",
        )
        self._owns_executor = executor is None
        self._futures: dict[int, Future[FilteredSessionPage]] = {}
        try:
            self._session_title = read_session_header(self.path).name
        except Exception:
            self._session_title = self.path.name

    @property
    def state(self) -> StoredSessionPageState:
        return StoredSessionPageState(
            path=self.path,
            session_title=self._session_title,
            page_size=self.page_size,
            generation=self._generation,
            page=self._page,
            filters_enabled=self._filters_enabled,
            available_filter_count=self._available_filter_set.active_count,
            active_filter_names=self._active_filter_set.active_names,
            filter_affects_visibility=self._active_filter_set.affects_visibility,
            loading=self._loading,
            error=self._error,
        )

    @property
    def available_filter_set(self) -> ActiveFilterSet:
        return self._available_filter_set

    @property
    def active_filter_set(self) -> ActiveFilterSet:
        return self._active_filter_set

    def start(self) -> StoredSessionPageState:
        return self._submit(0)

    def set_filters_enabled(self, enabled: bool) -> StoredSessionPageState:
        self._filters_enabled = bool(enabled)
        self._active_filter_set = (
            self._available_filter_set
            if self._filters_enabled
            else ActiveFilterSet((), scope="stored_session")
        )
        return self._submit(0)

    def reload_filters_if_changed(self) -> StoredSessionPageState | None:
        candidate = self._load_filter_set()
        if candidate.signature == self._available_filter_signature:
            return None
        self._available_filter_set = candidate
        self._available_filter_signature = candidate.signature
        if not self._filters_enabled:
            return self.state
        self._active_filter_set = candidate
        return self._submit(0)

    def request_page(self, start: int) -> StoredSessionPageState | None:
        requested = max(0, int(start))
        if (
            self._page is not None
            and requested == self._page_start
            and not self._loading
        ):
            return None
        return self._submit(requested)

    def first_page(self) -> StoredSessionPageState | None:
        return self.request_page(0)

    def previous_page(self) -> StoredSessionPageState | None:
        return self.request_page(max(0, self._page_start - self.page_size))

    def next_page(self) -> StoredSessionPageState | None:
        if self._page is None:
            return None
        return self.request_page(
            min(self.state.last_page_start, self._page_start + self.page_size)
        )

    def last_page(self) -> StoredSessionPageState | None:
        if self._page is None:
            return None
        return self.request_page(self.state.last_page_start)

    def poll(self) -> StoredSessionPageState | None:
        if self._closed:
            return None
        current = self._futures.get(self._generation)
        self._discard_finished_stale_futures()
        if current is None or not current.done():
            return None
        self._futures.pop(self._generation, None)
        try:
            page = current.result()
        except Exception as exc:
            self._loading = False
            self._error = str(exc)
            return self.state
        self._page = page
        self._page_start = page.loaded_from_visible_index
        self._loading = False
        self._error = ""
        return self.state

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._generation += 1
        for future in self._futures.values():
            future.cancel()
        self._futures.clear()
        if self._owns_executor:
            self._executor.shutdown(wait=False, cancel_futures=True)

    def _submit(self, start: int) -> StoredSessionPageState:
        if self._closed:
            raise RuntimeError("stored session controller is closed")
        self._generation += 1
        generation = self._generation
        self._page_start = max(0, int(start))
        self._loading = True
        self._error = ""
        self._futures[generation] = self._executor.submit(
            load_filtered_session_page,
            self.path,
            self._active_filter_set,
            max_rows=self.page_size,
            start=self._page_start,
        )
        return self.state

    def _load_filter_set(self) -> ActiveFilterSet:
        if self._database_path is None:
            return ActiveFilterSet((), scope="stored_session")
        return ActiveFilterSet(
            ProjectFilterRepository(self._database_path).list_presets(),
            scope="stored_session",
        )

    def _discard_finished_stale_futures(self) -> None:
        stale = [
            generation
            for generation, future in self._futures.items()
            if generation != self._generation and future.done()
        ]
        for generation in stale:
            future = self._futures.pop(generation)
            try:
                future.result()
            except Exception:
                pass


def _find_project_database(session_path: Path) -> Path | None:
    resolved = session_path.resolve()
    for directory in (resolved.parent, *resolved.parents):
        candidate = directory / ".crt" / "project.sqlite"
        if candidate.is_file():
            return candidate
    return None
