from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .isotp import PassiveIsoTpReassembler
from .models import CanFrame, DecodedEvent
from .sac import SAC_PROFILE, SacProfile
from .uds import UdsDecoder


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    events: list[DecodedEvent]
    completed_isotp_messages: int
    dropped_isotp_messages: int


class AnalysisEngine:
    def __init__(self, profile: SacProfile = SAC_PROFILE) -> None:
        self._reassembler = PassiveIsoTpReassembler()
        self._decoder = UdsDecoder(profile)

    def analyze(self, frames: Iterable[CanFrame]) -> AnalysisResult:
        self._reassembler.reset()
        events: list[DecodedEvent] = []
        completed = 0

        for frame in frames:
            for message in self._reassembler.feed(frame):
                completed += 1
                event = self._decoder.decode(message)
                if event is not None:
                    events.append(event)

        return AnalysisResult(
            events=events,
            completed_isotp_messages=completed,
            dropped_isotp_messages=self._reassembler.dropped_messages,
        )
