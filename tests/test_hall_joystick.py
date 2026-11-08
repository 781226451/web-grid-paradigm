from __future__ import annotations

import pytest

from web_grid_paradigm.geometry import Layout
from web_grid_paradigm.inputs import (
    HEADER,
    RAW_CENTER,
    RAW_MAX,
    RAW_MIN,
    SET_CENTER,
    DeviceContext,
    HallFrameParser,
    SerialJoystickOptions,
    SerialJoystickSource,
    build_input_source,
    normalize_axis,
)

LAYOUT = Layout.create(800, 600, 4, 4)


def make_frame(
    xx: int = RAW_CENTER,
    yy: int = RAW_CENTER,
    zz: int = RAW_CENTER,
    button: int = 0,
    address: int | None = None,
) -> bytes:
    """Build one frame exactly like the protocol document."""
    body = bytes(
        [
            (yy >> 8) & 0xFF,
            yy & 0xFF,
            (xx >> 8) & 0xFF,
            xx & 0xFF,
            (zz >> 8) & 0xFF,
            zz & 0xFF,
            button & 0xFF,
        ]
    )
    if address is None:
        return bytes((HEADER,)) + body + bytes((sum(body) & 0xFF,))
    payload = bytes((address,)) + body
    return bytes((HEADER,)) + payload + bytes((sum(payload) & 0xFF,))


class FakeTransport:
    """Minimal pyserial stand-in for headless tests."""

    def __init__(self, data: bytes = b"") -> None:
        self.data = bytearray(data)
        self.writes: list[bytes] = []
        self.closed = False

    def read(self, size: int = 1) -> bytes:
        if not self.data:
            return b""
        chunk = bytes(self.data[:size])
        del self.data[:size]
        return chunk

    def write(self, payload: bytes) -> int:
        self.writes.append(bytes(payload))
        return len(payload)

    def reset_input_buffer(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def make_source(
    data: bytes = b"",
    *,
    transport: FakeTransport | None = None,
    **options: object,
) -> tuple[SerialJoystickSource, FakeTransport]:
    fake = transport or FakeTransport(data)
    source = SerialJoystickSource(
        options=SerialJoystickOptions(port="fake", **options),
        context=DeviceContext(layout=LAYOUT),
        transport=fake,
        auto_thread=False,
    )
    source.open()
    return source, fake


# ----------------------------------------------------------------------
# protocol parser: framing, checksum, resynchronisation
# ----------------------------------------------------------------------
def test_pdf_example_frame_is_parsed() -> None:
    parser = HallFrameParser()
    frames = parser.feed(bytes.fromhex("FF0200020003FF0006"))
    assert len(frames) == 1
    frame = frames[0]
    assert (frame.xx, frame.yy, frame.zz) == (0x0200, 0x0200, 0x03FF)
    assert frame.button == 0
    assert frame.address is None
    assert frame.button_pressed is False


def test_addressed_pdf_example_is_parsed() -> None:
    parser = HallFrameParser(address=1)
    frames = parser.feed(bytes.fromhex("FF010200020002000007"))
    assert len(frames) == 1
    assert frames[0].address == 1
    assert (frames[0].xx, frames[0].yy, frames[0].zz) == (0x0200, 0x0200, 0x0200)

    wrong = HallFrameParser(address=2).feed(bytes.fromhex("FF010200020002000007"))
    assert wrong == []


def test_checksum_is_validated_and_parser_resynchronises() -> None:
    good = make_frame(xx=RAW_MAX, yy=RAW_MIN)
    corrupted = bytearray(good)
    corrupted[-1] ^= 0xFF
    parser = HallFrameParser()
    frames = parser.feed(bytes(corrupted) + good)
    assert len(frames) == 1
    assert frames[0].xx == RAW_MAX and frames[0].yy == RAW_MIN
    assert parser.invalid >= 1


def test_split_feeds_and_garbage_prefixes() -> None:
    frame = make_frame(xx=0x0300, yy=0x0100)
    parser = HallFrameParser()
    frames: list = []
    for byte in b"\xA5\x55\xAF" + frame:  # ACK prefix must be discarded
        frames.extend(parser.feed(bytes((byte,))))
    assert len(frames) == 1
    assert frames[0].xx == 0x0300 and frames[0].yy == 0x0100
    assert parser.discarded > 0


def test_normalize_axis_matches_protocol_ranges() -> None:
    assert normalize_axis(RAW_MIN) == pytest.approx(-1.0)
    assert normalize_axis(0x01FF) == pytest.approx(0.0)
    assert normalize_axis(RAW_CENTER) == pytest.approx(0.0)
    assert normalize_axis(0x0201) == pytest.approx(0.0)
    assert normalize_axis(RAW_MAX) == pytest.approx(1.0)
    assert normalize_axis(0) == pytest.approx(-1.0)  # clamped
    assert normalize_axis(0xFFFF) == pytest.approx(1.0)  # clamped


# ----------------------------------------------------------------------
# source: velocity mapping, state hold, buttons, status
# ----------------------------------------------------------------------
def test_factory_builds_a_working_joystick_strategy() -> None:
    source = build_input_source(
        "joystick",
        options=SerialJoystickOptions(port="fake"),
        context=DeviceContext(layout=LAYOUT),
    )
    assert isinstance(source, SerialJoystickSource)
    assert source.capabilities.category == "joystick"
    assert source.capabilities.n_buttons == 1
    assert source.read(now=0.0).samples == ()  # nothing until a frame arrives


def test_deflection_is_mapped_to_normalised_velocity() -> None:
    # right + up at full deflection: +1.4 norm/s on X, +1.867 norm/s on Y
    source, _ = make_source(data=make_frame(xx=RAW_MAX, yy=RAW_MAX))
    source.pump()
    read = source.read(now=10.0)
    assert len(read.samples) == 1
    sample = read.samples[0]
    assert sample.timestamp == pytest.approx(10.0)
    assert sample.vx == pytest.approx(560.0 / (800 / 2))
    assert sample.vy == pytest.approx(560.0 / (600 / 2))

    # left + down at full deflection
    source, _ = make_source(data=make_frame(xx=RAW_MIN, yy=RAW_MIN))
    source.pump()
    sample = source.read(now=10.0).samples[0]
    assert sample.vx == pytest.approx(-560.0 / (800 / 2))
    assert sample.vy == pytest.approx(-560.0 / (600 / 2))


def test_invert_flags_and_deadzone() -> None:
    source, _ = make_source(
        data=make_frame(xx=RAW_MAX, yy=RAW_MAX),
        invert_x=True,
        invert_y=True,
    )
    source.pump()
    sample = source.read(now=1.0).samples[0]
    assert sample.vx < 0 and sample.vy < 0

    just_off_centre = RAW_CENTER + 2  # ~0.004 normalised
    source, _ = make_source(
        data=make_frame(xx=just_off_centre, yy=RAW_CENTER),
        deadzone=0.05,
    )
    source.pump()
    sample = source.read(now=1.0).samples[0]
    assert sample.vx == pytest.approx(0.0)
    assert sample.vy == pytest.approx(0.0)


def test_state_is_held_between_device_frames() -> None:
    source, _ = make_source(data=make_frame(xx=RAW_MAX, yy=RAW_CENTER))
    source.pump()
    first = source.read(now=1.0).samples
    second = source.read(now=1.1).samples
    assert len(first) == len(second) == 1
    assert first[0].vx == pytest.approx(second[0].vx)


def test_button_edges_from_bit5() -> None:
    source, transport = make_source()
    pressed = make_frame(button=0x20)
    released = make_frame(button=0x00)

    def feed_and_read(payload: bytes, now: float):
        transport.data += payload
        source.pump()
        return source.read(now=now)

    assert [b.button for b in feed_and_read(pressed, 1.0).buttons] == [1]
    assert feed_and_read(pressed, 1.1).buttons == ()  # held: no repeat edge
    assert feed_and_read(released, 1.2).buttons == ()
    assert [b.button for b in feed_and_read(pressed, 1.3).buttons] == [1]


def test_center_calibration_command_is_sent_when_requested() -> None:
    source, transport = make_source(center_on_open=True)
    assert transport.writes == [SET_CENTER]


def test_status_reports_counters_and_parser_errors() -> None:
    good = make_frame(xx=RAW_MAX)
    corrupted = bytearray(good)
    corrupted[-1] ^= 0xFF
    source, _ = make_source(data=bytes(corrupted) + good)
    source.pump()
    source.read(now=1.0)
    status = source.status()
    assert status.name == "joystick"
    assert status.category == "joystick"
    assert status.connected is True
    assert status.frames == 1
    assert status.invalid >= 1
    assert status.device["protocol"] == "hall_rs232"
    assert status.device["baud"] == "9600"
    assert status.latency_ms is not None and status.latency_ms >= 0.0


def test_close_is_idempotent() -> None:
    source, transport = make_source()
    source.close()
    source.close()
    assert transport.closed is True
    assert source.status().connected is False


def test_addressed_source_reads_addressed_frames() -> None:
    source, _ = make_source(data=make_frame(xx=RAW_MAX, address=1), address=1)
    source.pump()
    sample = source.read(now=1.0).samples[0]
    assert sample.vx == pytest.approx(560.0 / (800 / 2))
    assert source.status().device["frame"] == "10"


def test_invalid_options_are_rejected() -> None:
    with pytest.raises(ValueError):
        SerialJoystickOptions(stream_mode="burst")
    with pytest.raises(ValueError):
        SerialJoystickOptions(address=0)
    with pytest.raises(ValueError):
        SerialJoystickOptions(speed_px_per_s=0.0)
