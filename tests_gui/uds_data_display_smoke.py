from __future__ import annotations

from app.logical_records import LogicalMessageRecord
from app.message_models import TransportKind, TransportMessage
from app.uds import UdsDecoder
from gui.stored_logical_message_panel import decoded_values_text


def _record(payload: bytes) -> LogicalMessageRecord:
    message = TransportMessage(
        sequence=0,
        first_timestamp_ns=0,
        last_timestamp_ns=0,
        transport=TransportKind.ISOTP,
        payload=payload,
        frame_sequences=(0,),
        arbitration_id=0x18DAF900,
        is_extended_id=True,
        source_address=0x00,
        destination_address=0xF9,
    )
    return LogicalMessageRecord.from_decoded(UdsDecoder().decode(message))


def main() -> None:
    vin = decoded_values_text(_record(b"\x62\xF1\x90XLRTE47MS0E123456"))
    assert "DID: 0xF190" in vin
    assert "ASCII: XLRTE47MS0E123456" in vin

    download = decoded_values_text(
        _record(bytes.fromhex("34 00 44 00 A2 00 00 00 00 11 EE"))
    )
    assert "Address: 0x00A20000" in download
    assert "Size: 0x000011EE" in download

    seed = decoded_values_text(_record(bytes.fromhex("67 07 5A 19 4C 00")))
    assert "Seed: 5A 19 4C 00" in seed

    transfer = decoded_values_text(_record(bytes.fromhex("36 03 DE AD BE EF")))
    assert "Block: 3" in transfer
    assert "Transfer data: DE AD BE EF" in transfer


if __name__ == "__main__":
    main()
