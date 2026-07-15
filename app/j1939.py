from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class J1939Identifier:
    can_id: int
    priority: int
    extended_data_page: int
    data_page: int
    pdu_format: int
    pdu_specific: int
    source_address: int
    destination_address: int | None
    pgn: int
    is_pdu1: bool


def decode_j1939_identifier(can_id: int) -> J1939Identifier:
    """Decode the field layout shared by J1939-style 29-bit identifiers.

    Decoding the fields does not by itself prove that a proprietary frame uses
    the J1939 protocol. CRT keeps that distinction at the protocol-decoder layer.
    """

    if not 0 <= can_id <= 0x1FFFFFFF:
        raise ValueError("J1939 identifier must fit in a 29-bit CAN ID")

    priority = (can_id >> 26) & 0x7
    extended_data_page = (can_id >> 25) & 0x1
    data_page = (can_id >> 24) & 0x1
    pdu_format = (can_id >> 16) & 0xFF
    pdu_specific = (can_id >> 8) & 0xFF
    source_address = can_id & 0xFF
    is_pdu1 = pdu_format < 240
    destination_address = pdu_specific if is_pdu1 else None

    pgn = (
        (extended_data_page << 17)
        | (data_page << 16)
        | (pdu_format << 8)
        | (0 if is_pdu1 else pdu_specific)
    )

    return J1939Identifier(
        can_id=can_id,
        priority=priority,
        extended_data_page=extended_data_page,
        data_page=data_page,
        pdu_format=pdu_format,
        pdu_specific=pdu_specific,
        source_address=source_address,
        destination_address=destination_address,
        pgn=pgn,
        is_pdu1=is_pdu1,
    )
