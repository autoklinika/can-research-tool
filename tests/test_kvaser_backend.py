from collections import deque
from threading import get_ident
from time import monotonic, sleep
from types import SimpleNamespace

import kvaser.backend as backend


class FakeFlags(int):
    pass


class FakeCanNoMsg(Exception):
    pass


class FakeChannel:
    def __init__(self, frames=None) -> None:
        self.driver = None
        self.bus_params = None
        self.bus_on = False
        self.closed = False
        self.frames = deque(frames or [_raw_frame(0x18FF0011, "01 02 03", 1234)])
        self.read_calls: list[int] = []
        self.read_thread_ids: list[int] = []
        self.bus_on_thread_id = None
        self.bus_off_thread_id = None
        self.close_thread_id = None

    def setBusOutputControl(self, driver) -> None:  # noqa: N802
        self.driver = driver

    def setBusParams(self, bitrate) -> None:  # noqa: N802
        self.bus_params = bitrate

    def busOn(self) -> None:  # noqa: N802
        self.bus_on = True
        self.bus_on_thread_id = get_ident()

    def busOff(self) -> None:  # noqa: N802
        self.bus_on = False
        self.bus_off_thread_id = get_ident()

    def close(self) -> None:
        self.closed = True
        self.close_thread_id = get_ident()

    def read(self, timeout: int):
        self.read_calls.append(timeout)
        self.read_thread_ids.append(get_ident())
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
        self.open_thread_id = None

    @staticmethod
    def getNumberOfChannels() -> int:  # noqa: N802
        return 1

    @staticmethod
    def ChannelData(number: int):  # noqa: N802
        assert number == 0
        return FakeChannelData()

    def openChannel(self, number: int):  # noqa: N802
        self.opened_with = number
        self.open_thread_id = get_ident()
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


def test_full_canlib_handle_lifecycle_stays_in_reader_thread(monkeypatch) -> None:
    api = FakeApi()
    monkeypatch.setattr(backend, "canlib", api)

    listener = backend.KvaserPassiveChannel(channel_number=0, bitrate=500_000)
    listener.open()
    assert _wait_until(lambda: bool(api.channel.read_thread_ids))
    listener.close()

    owner = api.open_thread_id
    assert owner is not None
    assert api.channel.bus_on_thread_id == owner
    assert set(api.channel.read_thread_ids) == {owner}
    assert api.channel.bus_off_thread_id == owner
    assert api.channel.close_thread_id == owner


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
    assert listener.received_count == 3
    assert listener.delivered_count == 0
    assert set(api.channel.read_calls) == {1}

    frames = [listener.read(timeout_ms=50) for _ in range(3)]
    assert [frame.arbitration_id for frame in frames if frame is not None] == [
        0x18FF0001,
        0x18FF0002,
        0x18FF0003,
    ]
    assert [frame.sequence for frame in frames if frame is not None] == [0, 1, 2]
    assert listener.delivered_count == 3

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
    assert listener.received_count == len(source_frames)
    assert listener.delivered_count == 0

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
    assert not hasattr(listener, "write")
    assert not hasattr(listener, "send")

    listener.close()


class FakeIoControl:
    def __init__(self) -> None:
        self.timer_scale = 1000


class TimedFakeChannel(FakeChannel):
    """Fake channel exposing CANlib timer controls (µs scale after setup)."""

    def __init__(self, frames=None, timer_now: int = 5_000) -> None:
        super().__init__(frames)
        self.iocontrol = FakeIoControl()
        self.timer_now = timer_now
        self.timer_scale_at_bus_on = None

    def busOn(self) -> None:  # noqa: N802
        self.timer_scale_at_bus_on = self.iocontrol.timer_scale
        super().busOn()

    def readTimer(self) -> int:  # noqa: N802
        return self.timer_now


def _read_all(listener, count: int):
    assert _wait_until(lambda: listener.prefetched_count == count)
    return [listener.read(timeout_ms=50) for _ in range(count)]


def test_hardware_timestamps_preserve_adapter_deltas(monkeypatch) -> None:
    api = FakeApi()
    api.channel = TimedFakeChannel(
        [
            _raw_frame(0x100, "01", 5_000),
            _raw_frame(0x101, "02", 5_200),
            _raw_frame(0x102, "03", 5_201),
        ],
        timer_now=5_000,
    )
    monkeypatch.setattr(backend, "canlib", api)

    listener = backend.KvaserPassiveChannel(channel_number=0, bitrate=500_000)
    listener.open()
    frames = _read_all(listener, 3)
    listener.close()

    assert api.channel.timer_scale_at_bus_on == backend.HARDWARE_TIMER_SCALE_US
    assert listener.timestamp_source == backend.TIMESTAMP_SOURCE_HARDWARE
    assert listener.timer_resolution_ns == 1_000
    stamps = [frame.timestamp_ns for frame in frames]
    assert stamps[1] - stamps[0] == 200_000
    assert stamps[2] - stamps[1] == 1_000
    assert [frame.source_timestamp for frame in frames] == [5_000, 5_200, 5_201]


def test_missing_timer_controls_fall_back_to_host_time(monkeypatch) -> None:
    api = FakeApi([_raw_frame(0x100, "01", 7)])
    monkeypatch.setattr(backend, "canlib", api)

    listener = backend.KvaserPassiveChannel(channel_number=0, bitrate=500_000)
    listener.open()
    frames = _read_all(listener, 1)
    listener.close()

    assert listener.timestamp_source == backend.TIMESTAMP_SOURCE_HOST
    assert listener.timer_resolution_ns is None
    assert frames[0].timestamp_ns > 0


def test_hardware_timestamp_mapper_unwraps_32_bit_counter() -> None:
    wrap = 1 << 32
    mapper = backend.HardwareTimestampMapper(
        tick_ns=1_000,
        hw_anchor=wrap - 10,
        host_anchor_ns=1_000_000_000,
    )

    before = mapper.to_host_ns(wrap - 5)
    after = mapper.to_host_ns(3)

    assert before == 1_000_000_000 + 5_000
    assert after - before == 8_000
    assert mapper.to_host_ns(4) - after == 1_000


def test_hardware_timestamp_mapper_rejects_invalid_tick() -> None:
    try:
        backend.HardwareTimestampMapper(tick_ns=0, hw_anchor=0, host_anchor_ns=0)
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("tick_ns=0 must be rejected")
