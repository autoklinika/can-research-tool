from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SacProfile:
    name: str = "DAF SAC"
    request_id: int = 0x18DA30F9
    response_id: int = 0x18DAF930
    did_names: dict[int, str] = field(
        default_factory=lambda: {
            0xF190: "VIN",
            0xF188: "Software version",
            0xF192: "Hardware version",
        }
    )

    def direction_for_id(self, arbitration_id: int) -> str:
        if arbitration_id == self.request_id:
            return "Tester → SAC"
        if arbitration_id == self.response_id:
            return "SAC → Tester"
        return "Inny CAN ID"


SAC_PROFILE = SacProfile()
