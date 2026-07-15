from crt.analysis import AnalysisEngine
from crt.models import CanFrame


def test_decodes_known_sac_session_and_vin() -> None:
    frames = [
        CanFrame(0.0, 0x18DA30F9, bytes.fromhex("02 10 03 00 00 00 00 00")),
        CanFrame(0.1, 0x18DAF930, bytes.fromhex("02 50 03 00 00 00 00 00")),
    ]

    result = AnalysisEngine().analyze(frames)

    assert result.completed_isotp_messages == 2
    assert [event.name for event in result.events] == [
        "DiagnosticSessionControl",
        "DiagnosticSessionControl positive response",
    ]
    assert result.events[0].direction == "Tester → SAC"
    assert result.events[1].direction == "SAC → Tester"
