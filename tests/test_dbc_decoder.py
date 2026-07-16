from pathlib import Path
from types import SimpleNamespace

import app.dbc as dbc_module
from app.message_models import ProtocolKind, TransportKind, TransportMessage


class FakeDbcMessage:
    def __init__(
        self,
        frame_id: int,
        name: str,
        *,
        is_extended: bool,
        decoded_value: float,
    ) -> None:
        self.frame_id = frame_id
        self.name = name
        self.is_extended_frame = is_extended
        self.length = 8
        self.cycle_time = 100
        self.senders = ["ECU"]
        self.signals = [SimpleNamespace(name="Value", unit="rpm")]
        self._decoded_value = decoded_value

    def decode(self, payload: bytes, **kwargs):
        assert payload
        assert kwargs["allow_truncated"] is True
        assert kwargs["allow_excess"] is True
        return {"Value": self._decoded_value}


class FakeDatabase:
    def __init__(self, messages) -> None:
        self.messages = messages


def _raw_message(can_id: int, *, extended: bool = True) -> TransportMessage:
    return TransportMessage(
        sequence=0,
        first_timestamp_ns=1,
        last_timestamp_ns=1,
        transport=TransportKind.RAW,
        payload=bytes.fromhex("01 02 03 04 05 06 07 08"),
        frame_sequences=(0,),
        arbitration_id=can_id,
        is_extended_id=extended,
    )


def test_dbc_decoder_prefers_exact_identifier(monkeypatch) -> None:
    exact = FakeDbcMessage(0x18F004A5, "ExactEEC1", is_extended=True, decoded_value=1200.0)
    wildcard = FakeDbcMessage(0x18F004FF, "WildcardEEC1", is_extended=True, decoded_value=900.0)

    monkeypatch.setattr(
        dbc_module.cantools.database,
        "load_file",
        lambda path, strict=False: FakeDatabase([wildcard, exact]),
    )

    decoder = dbc_module.DbcDecoder([Path("engine.dbc")])
    decoded = decoder.decode(_raw_message(0x18F004A5))

    assert decoded.protocol is ProtocolKind.DBC
    assert decoded.name == "DBC ExactEEC1"
    assert decoded.fields["dbc_match_mode"] == "exact-id"
    assert decoded.fields["signals"] == {"Value": 1200.0}


def test_dbc_decoder_matches_j1939_pdu2_with_wildcard_source(monkeypatch) -> None:
    wildcard = FakeDbcMessage(0x18F004FF, "EEC1", is_extended=True, decoded_value=1500.0)
    monkeypatch.setattr(
        dbc_module.cantools.database,
        "load_file",
        lambda path, strict=False: FakeDatabase([wildcard]),
    )

    decoder = dbc_module.DbcDecoder([Path("j1939.dbc")])
    message = _raw_message(0x18F004A5)

    assert decoder.matches(message) is True
    decoded = decoder.decode(message)
    assert decoded.name == "DBC EEC1"
    assert decoded.fields["dbc_match_mode"] == "j1939-address-aware"
    assert decoded.fields["signals"] == {"Value": 1500.0}


def test_dbc_decoder_matches_j1939_pdu1_with_wildcard_destination_and_source(
    monkeypatch,
) -> None:
    wildcard = FakeDbcMessage(0x18DAFFFF, "UDSLikePdu1", is_extended=True, decoded_value=1.0)
    monkeypatch.setattr(
        dbc_module.cantools.database,
        "load_file",
        lambda path, strict=False: FakeDatabase([wildcard]),
    )

    decoder = dbc_module.DbcDecoder([Path("pdu1.dbc")])
    message = _raw_message(0x18DA30F9)

    assert decoder.matches(message) is True
    decoded = decoder.decode(message)
    assert decoded.fields["dbc_match_mode"] == "j1939-address-aware"


def test_dbc_decoder_does_not_apply_to_reassembled_transport(monkeypatch) -> None:
    wildcard = FakeDbcMessage(0x18F004FF, "EEC1", is_extended=True, decoded_value=1.0)
    monkeypatch.setattr(
        dbc_module.cantools.database,
        "load_file",
        lambda path, strict=False: FakeDatabase([wildcard]),
    )
    decoder = dbc_module.DbcDecoder([Path("j1939.dbc")])
    message = TransportMessage(
        sequence=0,
        first_timestamp_ns=1,
        last_timestamp_ns=2,
        transport=TransportKind.J1939_BAM,
        payload=b"\x01\x02",
        frame_sequences=(0, 1),
        arbitration_id=0x18F004A5,
        is_extended_id=True,
    )

    assert decoder.matches(message) is False
