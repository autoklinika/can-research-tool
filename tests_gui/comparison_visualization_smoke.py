from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from gui.comparison_visualization import ComparisonVisualizationWidget


def main() -> None:
    app = QApplication.instance() or QApplication([])
    widget = ComparisonVisualizationWidget("Przed i po naprawie")
    widget.resize(1400, 850)
    widget.show()
    widget.set_payloads(_payloads())
    app.processEvents()

    data = widget.data
    assert data.new_count == 1
    assert data.missing_count == 1
    assert data.changed_payload_count == 1
    assert data.changed_sequence_count == 2
    assert data.largest_frequency_delta == 100.0
    assert widget.new_card.value_label.text() == "1"
    assert widget.missing_card.value_label.text() == "1"
    assert widget.payload_card.value_label.text() == "1"
    assert widget.sequence_card.value_label.text() == "2"
    assert widget.table.rowCount() == 3
    assert len(widget.frequency_panel.rows) == 1
    assert widget.heatmap.session_count == 2

    changed_row = _find_row(widget, "0x100")
    widget.table.selectRow(changed_row)
    app.processEvents()
    assert "0x100" in widget.inspector.key_label.text()
    assert widget.payload_preview.table.columnCount() == 2
    assert widget.payload_preview.table.item(2, 0).text() == "+1"

    widget.set_payloads(_large_payloads(620))
    app.processEvents()
    assert len(widget.data.rows) == 620
    assert widget.table.rowCount() == 100
    assert widget.rows_label.text() == "Wyświetlanie 1–100 z 620"
    assert widget.page_label.text() == "Strona 1 z 7"

    page_size_index = widget.page_size_combo.findData(500)
    assert page_size_index >= 0
    widget.page_size_combo.setCurrentIndex(page_size_index)
    app.processEvents()
    assert widget.table.rowCount() == 500
    assert widget.rows_label.text() == "Wyświetlanie 1–500 z 620"
    assert widget.page_label.text() == "Strona 1 z 2"
    assert widget.next_page_button.isEnabled()

    widget.next_page_button.click()
    app.processEvents()
    assert widget.table.rowCount() == 120
    assert widget.rows_label.text() == "Wyświetlanie 501–620 z 620"
    assert widget.page_label.text() == "Strona 2 z 2"
    assert not widget.next_page_button.isEnabled()
    assert widget.previous_page_button.isEnabled()

    widget.close()
    widget.deleteLater()
    app.sendPostedEvents()
    app.processEvents()
    print("Comparison visualization smoke: OK")


def _find_row(widget: ComparisonVisualizationWidget, text: str) -> int:
    for row in range(widget.table.rowCount()):
        item = widget.table.item(row, 1)
        if item is not None and text in item.text():
            return row
    raise AssertionError(f"row not found: {text}")


def _payloads() -> dict[str, dict]:
    statistics = {
        "schema": "crt.comparison_statistics",
        "sessions": [
            {"id": "before", "name": "Przed naprawą", "role": "base"},
            {"id": "after", "name": "Po naprawie", "role": "compared"},
        ],
        "message_keys": [
            _statistics_key(
                "0:STD:100:data",
                "100",
                baseline=_metrics(10, 10.0),
                current=_metrics(20, 20.0),
                reasons=["frequency_increase"],
                delta=100.0,
            ),
            _statistics_key(
                "0:STD:200:data",
                "200",
                baseline=_metrics(5, 5.0),
                current=None,
                reasons=["missing"],
                delta=None,
            ),
            _statistics_key(
                "0:STD:300:data",
                "300",
                baseline=None,
                current=_metrics(8, 8.0),
                reasons=["new"],
                delta=None,
            ),
        ],
    }
    payload = {
        "schema": "crt.payload_differences",
        "sessions": statistics["sessions"],
        "message_payload_profiles": [
            {
                "message_key": "0:STD:100:data",
                "channel": 0,
                "arbitration_id_hex": "100",
                "is_extended_id": False,
                "frame_kind": "data",
                "baseline": _profile("10", "20"),
                "sessions": [
                    {
                        "session_id": "before",
                        "session_name": "Przed naprawą",
                        "role": "base",
                        "payload_profile": _profile("10", "20"),
                        "comparison_to_baseline": [],
                    },
                    {
                        "session_id": "after",
                        "session_name": "Po naprawie",
                        "role": "compared",
                        "payload_profile": _profile("11", "20"),
                        "comparison_to_baseline": [
                            {
                                "change_type": "constant_byte_changed",
                                "byte_index": 0,
                            }
                        ],
                    },
                ],
            }
        ],
    }
    sequence = {
        "schema": "crt.message_sequence_differences",
        "summary": {"notable_change_count": 2},
        "sessions": statistics["sessions"],
        "ranked_changes": [
            {
                "sequence_text": "0:STD:100:data → 0:STD:300:data",
                "reasons": ["new_sequence"],
            },
            {
                "sequence_text": "0:STD:200:data → 0:STD:100:data",
                "reasons": ["missing_sequence"],
            },
        ],
    }
    return {
        statistics["schema"]: statistics,
        payload["schema"]: payload,
        sequence["schema"]: sequence,
    }


def _large_payloads(count: int) -> dict[str, dict]:
    statistics = {
        "schema": "crt.comparison_statistics",
        "sessions": [
            {"id": "before", "name": "Przed naprawą", "role": "base"},
            {"id": "after", "name": "Po naprawie", "role": "compared"},
        ],
        "message_keys": [
            _statistics_key(
                f"0:STD:{index:03X}:data",
                f"{index:03X}",
                baseline=_metrics(index + 1, 10.0),
                current=_metrics(index + 2, 10.0),
                reasons=[],
                delta=0.0,
            )
            for index in range(count)
        ],
    }
    return {statistics["schema"]: statistics}


def _statistics_key(
    message_key: str,
    arbitration_id_hex: str,
    *,
    baseline: dict | None,
    current: dict | None,
    reasons: list[str],
    delta: float | None,
) -> dict:
    return {
        "message_key": message_key,
        "channel": 0,
        "arbitration_id_hex": arbitration_id_hex,
        "is_extended_id": False,
        "frame_kind": "data",
        "baseline": baseline,
        "sessions": [
            {
                "session_id": "before",
                "session_name": "Przed naprawą",
                "role": "base",
                "statistics": baseline,
                "change": {"reasons": []},
            },
            {
                "session_id": "after",
                "session_name": "Po naprawie",
                "role": "compared",
                "statistics": current,
                "change": {
                    "reasons": reasons,
                    "frequency_delta_percent": delta,
                },
            },
        ],
    }


def _metrics(frame_count: int, frequency_hz: float) -> dict:
    return {
        "frame_count": frame_count,
        "mean_positive_frequency_hz": frequency_hz,
    }


def _profile(first: str, second: str) -> dict:
    return {
        "frame_count": 10,
        "byte_positions": [
            {
                "classification": "constant",
                "dominant_value_hex": first,
            },
            {
                "classification": "constant",
                "dominant_value_hex": second,
            },
        ],
    }


if __name__ == "__main__":
    main()
