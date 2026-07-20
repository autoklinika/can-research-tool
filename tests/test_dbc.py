from pathlib import Path

import pytest

from app.dbc import DbcDecoder, inspect_dbc
from app.logical_records import load_recent_logical_messages, logical_message_path_for_session
from app.message_models import TransportKind, TransportMessage
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.project_dbc import (
    active_project_dbc_paths,
    import_project_dbc,
    list_project_dbc,
    remove_project_dbc,
    set_project_dbc_enabled,
)
from app.session_stream import SessionStreamWriter
from app.stream_exports import MessageCsvStreamWriter


DBC_TEXT = '''VERSION ""

NS_ :
    NS_DESC_
    CM_
    BA_DEF_
    BA_
    VAL_
    CAT_DEF_
    CAT_
    FILTER
    BA_DEF_DEF_
    EV_DATA_
    ENVVAR_DATA_
    SGTYPE_
    SGTYPE_VAL_
    BA_DEF_SGTYPE_
    BA_SGTYPE_
    SIG_TYPE_REF_
    VAL_TABLE_
    SIG_GROUP_
    SIG_VALTYPE_
    SIGTYPE_VALTYPE_
    BO_TX_BU_
    BA_DEF_REL_
    BA_REL_
    BA_DEF_DEF_REL_
    BU_SG_REL_
    BU_EV_REL_
    BU_BO_REL_
    SG_MUL_VAL_

BS_:

BU_: ECU

BO_ 291 EGR_Status: 8 ECU
 SG_ EGR_Position : 0|8@1+ (0.4,0) [0|100] "%" Vector__XXX
 SG_ EGR_Command : 8|8@1+ (0.4,0) [0|100] "%" Vector__XXX
'''

EXTENDED_DBC_TEXT = DBC_TEXT.replace(
    "BO_ 291 EGR_Status: 8 ECU",
    "BO_ 2566869247 EngineData: 8 ECU",
).replace("EGR_Status", "EngineData") + '''
BO_ 2566844927 OtherPgn: 8 ECU
 SG_ OtherValue : 0|8@1+ (1,0) [0|255] "" Vector__XXX
'''


def _write_dbc(path: Path) -> Path:
    path.write_text(DBC_TEXT, encoding="utf-8")
    return path


def _raw_message() -> TransportMessage:
    return TransportMessage(
        sequence=0,
        first_timestamp_ns=0,
        last_timestamp_ns=0,
        transport=TransportKind.RAW,
        payload=bytes([125, 100, 0, 0, 0, 0, 0, 0]),
        frame_sequences=(0,),
        arbitration_id=0x123,
        is_extended_id=False,
    )


def _extended_raw_message(sequence: int = 0) -> TransportMessage:
    return TransportMessage(
        sequence=sequence,
        first_timestamp_ns=sequence,
        last_timestamp_ns=sequence,
        transport=TransportKind.RAW,
        payload=bytes([125, 100, 0, 0, 0, 0, 0, 0]),
        frame_sequences=(sequence,),
        arbitration_id=0x18FF50A5,
        is_extended_id=True,
    )


def test_dbc_decoder_reads_scaled_signals(tmp_path: Path) -> None:
    path = _write_dbc(tmp_path / "egr.dbc")
    inspection = inspect_dbc(path)
    assert inspection.message_count == 1
    assert inspection.standard_message_count == 1

    decoded = DbcDecoder((path,)).decode(_raw_message())
    assert decoded.protocol.value == "dbc"
    assert decoded.name == "DBC EGR_Status"
    assert decoded.fields["signals"]["EGR_Position"] == pytest.approx(50.0)
    assert decoded.fields["signals"]["EGR_Command"] == pytest.approx(40.0)


def test_extended_dbc_lookup_and_payload_decode_are_cached(tmp_path: Path) -> None:
    path = tmp_path / "j1939.dbc"
    path.write_text(EXTENDED_DBC_TEXT, encoding="utf-8")
    decoder = DbcDecoder((path,))

    first = decoder.decode_if_matches(_extended_raw_message())
    assert first is not None
    assert first.name == "DBC EngineData"
    assert first.fields["dbc_match_mode"] == "j1939-address-aware"
    assert decoder.cache_stats["last_candidate_count"] == 1

    for sequence in range(1, 101):
        decoded = decoder.decode_if_matches(_extended_raw_message(sequence))
        assert decoded is not None
        assert decoded.fields["signals"]["EGR_Position"] == pytest.approx(50.0)

    stats = decoder.cache_stats
    assert stats["match_cache_misses"] == 1
    assert stats["match_cache_hits"] >= 100
    assert stats["payload_cache_misses"] == 1
    assert stats["payload_cache_hits"] >= 100
    assert stats["match_cache_entries"] == 1


def test_project_dbc_import_enable_disable_and_remove(tmp_path: Path) -> None:
    project = CrtProject.create(tmp_path / "project", name="DBC project")
    source = _write_dbc(tmp_path / "egr.dbc")

    record = import_project_dbc(project, source)
    copied = project.absolute_path(record.relative_path)
    assert copied.is_file()
    assert copied.parent == project.root / "decoders" / "dbc"
    assert record.enabled is True
    assert record.message_count == 1
    assert list_project_dbc(project)[0].id == record.id
    assert active_project_dbc_paths(project) == (copied,)

    set_project_dbc_enabled(project, record.id, False)
    assert active_project_dbc_paths(project) == ()
    assert list_project_dbc(project)[0].enabled is False

    set_project_dbc_enabled(project, record.id, True)
    assert active_project_dbc_paths(project) == (copied,)

    remove_project_dbc(project, record.id)
    assert list_project_dbc(project) == []
    assert not copied.exists()


def test_saved_dbc_result_returns_to_unknown_when_decoder_is_disabled(
    tmp_path: Path,
) -> None:
    dbc_path = _write_dbc(tmp_path / "egr.dbc")
    session_path = tmp_path / "capture.crt.jsonl"
    frame = CanFrame(
        sequence=0,
        timestamp_ns=0,
        arbitration_id=0x123,
        data=bytes([125, 100, 0, 0, 0, 0, 0, 0]),
    )
    with SessionStreamWriter(
        CaptureSession(name="capture", source="test"),
        session_path,
    ) as writer:
        writer.append(frame)

    dbc_decoded = DbcDecoder((dbc_path,)).decode(_raw_message())
    with MessageCsvStreamWriter(logical_message_path_for_session(session_path)) as writer:
        writer.append(dbc_decoded)

    enabled, total, source = load_recent_logical_messages(
        session_path,
        max_rows=10,
        dbc_paths=(dbc_path,),
    )
    assert total == 1
    assert source == "messages-csv+dbc"
    assert enabled[0].protocol == "dbc"
    assert enabled[0].fields["signals"]["EGR_Position"] == pytest.approx(50.0)

    disabled, total, source = load_recent_logical_messages(
        session_path,
        max_rows=10,
        dbc_paths=(),
    )
    assert total == 1
    assert source == "messages-csv"
    assert disabled[0].protocol == "unknown"
    assert disabled[0].name == "Unknown / proprietary CAN message"
