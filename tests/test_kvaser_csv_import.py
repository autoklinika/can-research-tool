from pathlib import Path

from kvaser.csv_import import import_monitor_csv


def test_imports_existing_kvaser_monitor_format(tmp_path: Path) -> None:
    source = tmp_path / "can_log.csv"
    source.write_text(
        "timestamp;can_id;type;dlc;data;uds;ascii;filter_active;filter_text\n"
        "1000;18DAF900;EXT;8;03 7F 22 31 FF FF FF FF;;;no;\n"
        "1010;123;STD;2;AA BB;;;no;\n",
        encoding="utf-8-sig",
    )

    result = import_monitor_csv(source)

    assert result.warnings == ()
    assert len(result.session.frames) == 2
    first, second = result.session.frames
    assert first.timestamp_ns == 0
    assert second.timestamp_ns == 10_000_000
    assert first.source_timestamp == 1000
    assert first.arbitration_id == 0x18DAF900
    assert first.is_extended_id is True
    assert second.arbitration_id == 0x123
    assert second.is_extended_id is False
    assert second.data == bytes.fromhex("AA BB")


def test_reports_dlc_mismatch_without_losing_frame(tmp_path: Path) -> None:
    source = tmp_path / "can_log.csv"
    source.write_text(
        "timestamp;can_id;type;dlc;data;uds;ascii;filter_active;filter_text\n"
        "1;321;STD;8;01 02;;;no;\n",
        encoding="utf-8",
    )

    result = import_monitor_csv(source)

    assert len(result.session.frames) == 1
    assert len(result.warnings) == 1
    assert "DLC=8" in result.warnings[0]
