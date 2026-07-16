from collections import deque
from time import monotonic, sleep
from types import SimpleNamespace

import kvaser.backend as backend


class FakeFlags(int):
    pass


class FakeCanNoMsg(Exception):
    pass


class FakeIoControl:
    def __init__(self) -> None:
        self.local_txecho = True


class FakeChannel:
    def __init__(self, frames=None) -> None:
        self.driver = None
        self.bus_params = None
        self.bus_on = False
        self.closed = False
        self.iocontrol = FakeIoControl()
        self.frames = deque(frames or [_raw_frame(0x18FF0011, "01 02 03", 1234)])
        self.read_calls: list[int] = []

    def setBusOutputControl(self, driver) -> None:  # noqa: N802
        self.driver = driver

    def setBusParams(self, bitrate) -> None:  # noqa: N802
        self.bus_params = bitrate

    def busOn(self) -> None:  # noqa: N802
        self.bus_on = True

    def busOff(self) -> None:  # noqa: N802
        self.bus_on = False

    def close(self) -> None:
        self.closed = True

    def read(self, timeout: int):
        self.read_calls.append(timeout)
        if self.frames:
            return self.frames.popleft()
        sleep(max(0.0005, timeout / 1000.0))
        raise FakeCanNoMsg


class FakeChannelData:
    channel_name = "Fake Kvaser"
    card_serial_no = 123
    card_upc_no = "00-00000-00000-0"
    channel_cap = 1


class FakeApi:
    ChannelCap = SimpleNamespace(SILENT_MODE=1)
    Driver = SimpleNamespace(SILENT=99, NORMAL=44)
    Bitrate = SimpleNamespace(
        BITRATE_10K=10,
        BITRATE_50K=50,
        BITRATE_62K=62,
        BITRATE_83K=83,
        BITRATE_100K=100,
        BITRATE_125K=125,
        BITRATE_250K=250,
        BITRATE_500K=500,
        BITRATE_1M=1000,
    )
    MessageFlag = SimpleNamespace(EXT=4, RTR=1, ERROR_FRAME=32)
    CanNoMsg = FakeCanNoMsg

    def __init__(self, frames=None) -> None:
        self.channel = FakeChannel(frames)
        self.opened_with = None

    @staticmethod
    def getNumberOfChannels() -> int:  # noqa: N802
        return 1

    @staticmethod
    def ChannelData(number: int):  # noqa: N802
        assert number == 0
        return FakeChannelData()

    def openChannel(self, number: int):  # noqa: N802
        self.opened_with = number
        return self.channel


def _raw_frame(can_id: int, data: str, timestamp: int):
    payload = bytes.fromhex(data)
    return SimpleNamespace(
        id=can_id,
        data=payload,
        dlc=len(payload),
        flags=FakeFlags(4),
        timestamp=timestamp,
    )


def _wait_until(predicate, timeout_s: float = 0.5) -> bool:
    deadline = monotonic() + timeout_s
    while monotonic() < deadline:
        if predicate():
            return True
        sleep(0.001)
    return bool(predicate())


def test_bench_mode_matches_known_good_channel_setup(monkeypatch) -> None:
    api = FakeApi()
    monkeypatch.setattr(backend, "canlib", api)

    listener = backend.KvaserPassiveChannel(channel_number=0, bitrate=250_000)
    listener.open()

    assert api.opened_with == 0
    assert api.channel.driver == api.Driver.NORMAL
    assert api.channel.bus_params == api.Bitrate.BITRATE_250K
    assert api.channel.iocontrol.local_txecho is False
    assert api.channel.bus_on is True
    assert not hasattr(listener, "write")
    assert not hasattr(listener, "send")

    frame = listener.read(timeout_ms=100)
    assert frame is not None
    assert frame.arbitration_id == 0x18FF0011
    assert frame.is_extended_id is True
    assert frame.source_timestamp == 1234
    assert api.channel.read_calls
    assert set(api.channel.read_calls) == {1}

    listener.close()
    assert api.channel.bus_on is False
    assert api.channel.closed is True


def test_reader_thread_drains_canlib_before_processing(monkeypatch) -> None:
    api = FakeApi(
        [
            _raw_frame(0x18FF0001, "01", 100),
            _raw_frame(0x18FF0002, "02", 101),
            _raw_frame(0x18FF0003, "03", 102),
        ]
    )
    monkeypatch.setattr(backend, "canlib", api)

    listener = backend.KvaserPassiveChannel(channel_number=0, bitrate=250_000)
    listener.open()

    assert _wait_until(lambda: listener.prefetched_count == 3)
    assert api.channel.frames == deque()
    assert set(api.channel.read_calls) == {1}

    frames = [listener.read(timeout_ms=50) for _ in range(3)]
    assert [frame.arbitration_id for frame in frames if frame is not None] == [
        0x18FF0001,
        0x18FF0002,
        0x18FF0003,
    ]
    assert [frame.sequence for frame in frames if frame is not None] == [0, 1, 2]

    listener.close()


def test_reader_continues_while_consumer_is_idle(monkeypatch) -> None:
    source_frames = [
        _raw_frame(0x100 + index, f"{index:02X}", index)
        for index in range(64)
    ]
    api = FakeApi(source_frames)
    monkeypatch.setattr(backend, "canlib", api)

    listener = backend.KvaserPassiveChannel(channel_number=0, bitrate=500_000)
    listener.open()

    assert _wait_until(lambda: listener.prefetched_count == len(source_frames))
    assert not api.channel.frames
    assert api.channel.bus_params == api.Bitrate.BITRATE_500K

    listener.close()


def test_listen_only_mode_forces_silent_driver(monkeypatch) -> None:
    api = FakeApi()
    monkeypatch.setattr(backend, "canlib", api)

    listener = backend.KvaserPassiveChannel(
        channel_number=0,
        bitrate=250_000,
        mode=backend.KvaserReceiveMode.LISTEN_ONLY,
    )
    listener.open()

    assert api.channel.driver == api.Driver.SILENT
    assert api.channel.bus_params == api.Bitrate.BITRATE_250K
    assert api.channel.iocontrol.local_txecho is False
    assert not hasattr(listener, "write")
    assert not hasattr(listener, "send")

    listener.close()
