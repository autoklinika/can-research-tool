from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtWidgets import QApplication, QTableView

from app.query_engine import QueryEngine
from app.search_engine import SearchQuery
from gui.logical_search_index import LogicalSqlSearchIndex
from gui.search_index_registry import SearchIndexRegistry
from gui.stored_logical_sql_model import StoredLogicalSqlModel


def _create_cache(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY,
                sequence INTEGER NOT NULL,
                first_timestamp_ns INTEGER NOT NULL,
                last_timestamp_ns INTEGER NOT NULL,
                protocol TEXT NOT NULL,
                transport TEXT NOT NULL,
                name TEXT NOT NULL,
                arbitration_id INTEGER,
                is_extended_id INTEGER NOT NULL,
                pgn INTEGER,
                source_address INTEGER,
                destination_address INTEGER,
                sender TEXT NOT NULL,
                identity_text TEXT NOT NULL,
                complete INTEGER NOT NULL,
                frame_sequences_json TEXT NOT NULL,
                payload BLOB NOT NULL,
                error TEXT NOT NULL,
                confidence REAL NOT NULL,
                fields_json TEXT NOT NULL
            );
            """
        )
        fields = {
            "signals": {"EngineSpeed": 1234.5},
            "signal_units": {"EngineSpeed": "rpm"},
            "DbcFile": "J1939.dbc",
            "DbcMatchMode": "J1939-PGN",
        }
        connection.execute(
            """
            INSERT INTO messages(
                id, sequence, first_timestamp_ns, last_timestamp_ns,
                protocol, transport, name, arbitration_id, is_extended_id,
                pgn, source_address, destination_address, sender,
                identity_text, complete, frame_sequences_json, payload,
                error, confidence, fields_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                1,
                1_000_000,
                1_000_000,
                "j1939",
                "single-frame",
                "EEC1",
                0x0CF00400,
                1,
                0xF004,
                0,
                255,
                "SA 00",
                "eec1",
                1,
                "[1]",
                sqlite3.Binary(bytes.fromhex("0011223344556677")),
                "",
                1.0,
                json.dumps(fields),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def main() -> None:
    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory() as temporary:
        cache_path = Path(temporary) / "sample.logical.sqlite"
        _create_cache(cache_path)

        model = StoredLogicalSqlModel()
        model.set_cache(cache_path)
        table = QTableView()
        table.setModel(model)

        registry = SearchIndexRegistry()
        index = registry.index_for_table(table)
        assert isinstance(index, LogicalSqlSearchIndex)
        assert index.is_ready
        assert index.progress == (1, 1)

        result = QueryEngine().search(index.snapshot(), SearchQuery("EngineSpeed"))
        assert [hit.row for hit in result.hits] == [0]
        assert result.scanned_documents == 1

        # A second request reuses the same ready adapter and never creates a
        # time-sliced in-memory table index.
        reused = registry.index_for_table(table)
        assert reused is index
        assert index.is_ready
        assert len(registry._indexes) == 0

        registry.close()
        model.close_cache()
        table.deleteLater()
        model.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    main()
