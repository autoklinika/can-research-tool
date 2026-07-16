from collections import deque
from types import SimpleNamespace

import kvaser.backend as backend


class FakeFlags(int):
    pass


class FakeCanNoMsg(Exception):
    pass


class FakeIoControl:
    def __init__(self) -> None:
        self.local_txecho = True
        self.flushed = False

    def flush_rx_buffer(self) -> None:
        self.flushed = True


class FakeChannel:
    def __init__(self, frames=None) -> None:
        self.driver = None
        self.bus_on = False
        self.closed = False
        self.iocontrol = FakeIoControl()
        self.frames = deque(frames or [_raw_frame(0x18FF0011, "01 02 03", 1234)])
        self.read_calls: list[int] = []

    def setBusOutputControl(self, driver) -> None:  # noqa: N802
        self.driver = driver

    def busOn(self) -> None:  # noqa: N802
        self.bus_on = True

    def busOff(self) -> None:  # noqa: N802
        self.bus_on = False

    def close(self) -> None:
        self.closed = True

    def read(self, timeout: int):
        self.read_calls.append(timeout)
        if not self.frames:
            raise FakeCanNoMsg
        return self.frames.popleft()


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

    def openChannel(self, number: int, *, bitrate):  # noqa: N802
        self.opened_with = (number, bitrate)
        return self.channel


def _raw_frame(can_id: int, data: str, timestamp: int):
    return SimpleNamespace(
        id=can_id,
        data=bytes.fromhex(data),
        flags=FakeFlags(4),
        timestamp=timestamp,
    )


def test_bench_mode_acknowledges_frames_but_has_no_tx_api(monkeypatch) -> None:
    api = FakeApi()
    monkeypatch.setattr(backend, "canlib", api)

    listener = backend.KvaserPassiveChannel(channel_number=0, bitrate=250_000)
    listener.open()

    assert api.opened_with == (0, api.Bitrate.BITRATE_250K)
    assert api.channel.driver == api.Driver.NORMAL
    assert api.channel.iocontrol.local_txecho is False
    assert api.channel.iocontrol.flushed is True
    assert api.channel.bus_on is True
    assert not hasattr(listener, "write")
    assert not hasattr(listener, "send")

    frame = listener.read(timeout_ms=25)
    assert frame is not None
    assert frame.arbitration_id == 0x18FF0011
    assert frame.is_extended_id is True
    assert frame.source_timestamp == 1234
    assert api.channel.read_calls == [25, 0]

    listener.close()
    assert api.channel.bus_on is False
    assert api.channel.closed is True


def test_read_prefetches_queued_frames_before_processing(monkeypatch) -> None:
    api = FakeApi(
        [
            _raw_frame(0x18FF0001, "01", 100),
            _raw_frame(0x18FF0002, "02", 101),
            _raw_frame(0x18FF0003, "03", 102),
        ]
    )
    monkeypatch.setattr(backend, "canlib", api)

    listener = backend.KvaserPassiveChannel(
        channel_number=0,
        bitrate=250_000,
        prefetch_limit=16,
    )
    listener.open()

    first = listener.read(timeout_ms=25)
    assert first is not None
    assert first.arbitration_id == 0x18FF0001
    assert listener.prefetched_count == 2
    assert api.channel.read_calls == [25, 0, 0, 0]

    second = listener.read(timeout_ms=25)
    third = listener.read(timeout_ms=25)
    assert second is not None and second.arbitration_id == 0x18FF0002
    assert third is not None and third.arbitration_id == 0x18FF0003
    assert [first.sequence, second.sequence, third.sequence] == [0, 1, 2]
    assert api.channel.read_calls == [25, 0, 0, 0]


def test_prefetch_limit_is_bounded(monkeypatch) -> None:
    api = FakeApi(
        [
            _raw_frame(0x100 + index, f"{index:02X}", index)
            for index in range(5)
        ]
    )
    monkeypatch.setattr(backend, "canlib", api)

    listener = backend.KvaserPassiveChannel(
        channel_number=0,
        bitrate=250_000,
        prefetch_limit=3,
    )
    listener.open()

    first = listener.read(timeout_ms=10)
    assert first is not None
    assert listener.prefetched_count == 2
    assert api.channel.read_calls == [10, 0, 0]


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
    assert api.channel.iocontrol.local_txecho is False
    assert not hasattr(listener, "write")
    assert not hasattr(listener, "send")
