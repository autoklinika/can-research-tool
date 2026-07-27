from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import Qt, QUrl, Signal, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.help_catalog import (
    HELP_CATEGORY_ORDER,
    HELP_TOPICS,
    HelpTopic,
    help_topic,
    render_help_home_html,
    render_help_topic_html,
    search_help_topics,
)

_HOME_ID = "__home__"
_TOPIC_ROLE = Qt.ItemDataRole.UserRole


class HelpCenterWidget(QWidget):
    """Searchable in-application documentation for CAN Research Tool."""

    topic_opened = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("helpCenterWidget")
        self._history: list[str] = []
        self._history_index = -1
        self._current_page_id = ""
        self._visible_topic_ids: tuple[str, ...] = ()

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)

        header = QHBoxLayout()
        title = QLabel("Pomoc CAN Research Tool", self)
        title.setObjectName("helpCenterTitle")
        font = title.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 5)
        title.setFont(font)
        header.addWidget(title)
        header.addStretch(1)

        self.back_button = QPushButton("Wstecz", self)
        self.back_button.setObjectName("helpBackButton")
        self.back_button.clicked.connect(self.go_back)
        header.addWidget(self.back_button)

        self.forward_button = QPushButton("Dalej", self)
        self.forward_button.setObjectName("helpForwardButton")
        self.forward_button.clicked.connect(self.go_forward)
        header.addWidget(self.forward_button)

        self.home_button = QPushButton("Start pomocy", self)
        self.home_button.setObjectName("helpHomeButton")
        self.home_button.clicked.connect(self.show_home)
        header.addWidget(self.home_button)
        root.addLayout(header)

        search_row = QHBoxLayout()
        search_label = QLabel("Szukaj w pomocy:", self)
        search_row.addWidget(search_label)
        self.search_edit = QLineEdit(self)
        self.search_edit.setObjectName("helpSearchEdit")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setPlaceholderText(
            "np. import logu, filtr, jitter, DID, 0x78, brak wyników…"
        )
        self.search_edit.textChanged.connect(self._rebuild_tree)
        self.search_edit.returnPressed.connect(self._open_first_visible_topic)
        search_row.addWidget(self.search_edit, 1)
        self.clear_search_button = QPushButton("Wyczyść", self)
        self.clear_search_button.setObjectName("helpClearSearchButton")
        self.clear_search_button.clicked.connect(self.search_edit.clear)
        search_row.addWidget(self.clear_search_button)
        root.addLayout(search_row)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setObjectName("helpCenterSplitter")
        root.addWidget(splitter, 1)

        navigation = QWidget(splitter)
        navigation_layout = QVBoxLayout(navigation)
        navigation_layout.setContentsMargins(0, 0, 0, 0)
        nav_label = QLabel("Spis tematów", navigation)
        nav_font = nav_label.font()
        nav_font.setBold(True)
        nav_label.setFont(nav_font)
        navigation_layout.addWidget(nav_label)

        self.topic_tree = QTreeWidget(navigation)
        self.topic_tree.setObjectName("helpTopicTree")
        self.topic_tree.setHeaderHidden(True)
        self.topic_tree.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.topic_tree.itemSelectionChanged.connect(
            self._tree_selection_changed
        )
        navigation_layout.addWidget(self.topic_tree, 1)
        splitter.addWidget(navigation)

        content = QWidget(splitter)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        self.browser = QTextBrowser(content)
        self.browser.setObjectName("helpBrowser")
        self.browser.setOpenExternalLinks(False)
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(self._anchor_clicked)
        content_layout.addWidget(self.browser, 1)
        self.status_label = QLabel(content)
        self.status_label.setObjectName("helpStatusLabel")
        self.status_label.setWordWrap(True)
        content_layout.addWidget(self.status_label)
        splitter.addWidget(content)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([330, 1050])

        self.search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.search_shortcut.activated.connect(self.focus_search)
        self.back_shortcut = QShortcut(QKeySequence("Alt+Left"), self)
        self.back_shortcut.activated.connect(self.go_back)
        self.forward_shortcut = QShortcut(QKeySequence("Alt+Right"), self)
        self.forward_shortcut.activated.connect(self.go_forward)

        self._rebuild_tree("")
        self._navigate(_HOME_ID, record=True)

    @property
    def current_topic_id(self) -> str:
        return "" if self._current_page_id == _HOME_ID else self._current_page_id

    @property
    def visible_topic_ids(self) -> tuple[str, ...]:
        return self._visible_topic_ids

    @Slot()
    def focus_search(self) -> None:
        self.search_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search_edit.selectAll()

    @Slot()
    def show_home(self) -> None:
        self._navigate(_HOME_ID, record=True)

    def open_topic(self, topic_id: str) -> None:
        help_topic(topic_id)
        self._navigate(topic_id, record=True)

    @Slot()
    def go_back(self) -> None:
        if self._history_index <= 0:
            return
        self._history_index -= 1
        self._navigate(
            self._history[self._history_index],
            record=False,
        )

    @Slot()
    def go_forward(self) -> None:
        if self._history_index >= len(self._history) - 1:
            return
        self._history_index += 1
        self._navigate(
            self._history[self._history_index],
            record=False,
        )

    @Slot(str)
    def _rebuild_tree(self, query: str) -> None:
        topics = search_help_topics(query)
        current = self.current_topic_id
        self.topic_tree.blockSignals(True)
        self.topic_tree.clear()
        grouped: dict[str, list[HelpTopic]] = defaultdict(list)
        for topic in topics:
            grouped[topic.category].append(topic)
        for category in HELP_CATEGORY_ORDER:
            category_topics = grouped.get(category, [])
            if not category_topics:
                continue
            category_item = QTreeWidgetItem([category])
            category_item.setFlags(
                category_item.flags() & ~Qt.ItemFlag.ItemIsSelectable
            )
            category_font = category_item.font(0)
            category_font.setBold(True)
            category_item.setFont(0, category_font)
            self.topic_tree.addTopLevelItem(category_item)
            for topic in category_topics:
                item = QTreeWidgetItem([topic.title])
                item.setData(0, _TOPIC_ROLE, topic.id)
                item.setToolTip(0, topic.summary)
                category_item.addChild(item)
                if topic.id == current:
                    self.topic_tree.setCurrentItem(item)
            category_item.setExpanded(True)
        self.topic_tree.blockSignals(False)
        self._visible_topic_ids = tuple(topic.id for topic in topics)
        if query.strip():
            self.status_label.setText(
                f"Wyniki wyszukiwania: {len(topics)} tematów. "
                "Naciśnij Enter, aby otworzyć pierwszy wynik."
            )
        else:
            self.status_label.setText(
                f"Dostępne tematy: {len(HELP_TOPICS)}. "
                "F1 otwiera Pomoc, Ctrl+F ustawia fokus w wyszukiwarce."
            )

    @Slot()
    def _open_first_visible_topic(self) -> None:
        if self._visible_topic_ids:
            self.open_topic(self._visible_topic_ids[0])

    @Slot()
    def _tree_selection_changed(self) -> None:
        items = self.topic_tree.selectedItems()
        if not items:
            return
        topic_id = items[0].data(0, _TOPIC_ROLE)
        if topic_id:
            self.open_topic(str(topic_id))

    @Slot(QUrl)
    def _anchor_clicked(self, url: QUrl) -> None:
        if url.scheme() != "help":
            return
        if url.host() == "topic":
            topic_id = url.path().lstrip("/")
            if topic_id:
                self.open_topic(topic_id)

    def _navigate(self, page_id: str, *, record: bool) -> None:
        if page_id == _HOME_ID:
            html = render_help_home_html()
            title = "Start pomocy"
        else:
            topic = help_topic(page_id)
            html = render_help_topic_html(topic)
            title = topic.title

        if record:
            if self._history_index < len(self._history) - 1:
                del self._history[self._history_index + 1 :]
            if not self._history or self._history[-1] != page_id:
                self._history.append(page_id)
            self._history_index = len(self._history) - 1

        self._current_page_id = page_id
        self.browser.setHtml(html)
        self.browser.verticalScrollBar().setValue(0)
        self._select_tree_topic(page_id)
        self._update_history_buttons()
        if page_id != _HOME_ID:
            self.topic_opened.emit(page_id)
        self.status_label.setText(
            f"Otwarty temat: {title}. "
            "Alt+Left i Alt+Right przechodzą po historii."
        )

    def _select_tree_topic(self, page_id: str) -> None:
        if page_id == _HOME_ID:
            self.topic_tree.blockSignals(True)
            self.topic_tree.clearSelection()
            self.topic_tree.blockSignals(False)
            return
        iterator = _iter_tree_items(self.topic_tree)
        for item in iterator:
            if item.data(0, _TOPIC_ROLE) == page_id:
                self.topic_tree.blockSignals(True)
                self.topic_tree.setCurrentItem(item)
                self.topic_tree.scrollToItem(item)
                self.topic_tree.blockSignals(False)
                return

    def _update_history_buttons(self) -> None:
        self.back_button.setEnabled(self._history_index > 0)
        self.forward_button.setEnabled(
            0 <= self._history_index < len(self._history) - 1
        )


def _iter_tree_items(tree: QTreeWidget):
    for top_index in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(top_index)
        yield top
        for child_index in range(top.childCount()):
            yield top.child(child_index)


__all__ = ["HelpCenterWidget"]
