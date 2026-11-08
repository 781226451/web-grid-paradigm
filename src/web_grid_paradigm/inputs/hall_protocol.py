"""Hall-effect joystick RS232/RS422 protocol.

Protocol summary (manufacturer document, 9/10-byte frames, 9600 8N1).

Universal frame (default, no address)::

    FF YYH YYL XXH XXL ZZH ZZL Button CH
 
* ``YY``/``XX``/``ZZ`` are big-endian raw axis values in ``0x0030..0x03D0``
  with centre ``0x0200``; the lower half is the negative direction and the
  upper half the positive direction (X: left/right, Y: down/up, Z: twist).
* ``Button`` bit 5 (``0x20``) is the joystick trigger; other bits are zero.
* ``CH = (XXH + XXL + YYH + YYL + ZZH + ZZL + Button) & 0xFF``.

Addressed frame (bus mode, when an address is configured)::

    FF Add YYH YYL XXH XXL ZZH ZZL Button CH
    CH = (Add + XXH + XXL + YYH + YYL + ZZH + ZZL + Button) & 0xFF

The joystick sends frames when the stick changes and/or periodically
(10-50 ms, factory configurable), so the parser is rate independent and
resynchronises on the ``0xFF`` header after a corrupted frame.

PC -> joystick commands (hex)::

    AA 55 AF 00      set the current position as centre (calibration)
    AA 55 AF 01      query the position once; stops the periodic stream!
    A5 55 01 xx FF   baud rate (00=9600, 01=19200, 02=115200), answered by ACK
    A5 55 03 Add FF  set address 1..64
    A5 55 05 00 FF   cancel address (back to the universal protocol)

The parser is pure Python and independent of pyserial/PsychoPy so it can be
unit-tested with byte streams; :class:`SerialJoystickSource` owns the device.
"""

from __future__ import annotations

from dataclasses import dataclass

# Frame layout ---------------------------------------------------------------
HEADER = 0xFF
FRAME_LEN_UNIVERSAL = 9
FRAME_LEN_ADDRESSED = 10

# Axis range from the protocol table ----------------------------------------
RAW_MIN = 0x0030
RAW_MAX = 0x03D0
RAW_CENTER = 0x0200
# 463: (0x01FF - 0x0030) and (0x03D0 - 0x0201); the centre is a 3-count plateau
RAW_HALF_RANGE = (RAW_CENTER - 1) - RAW_MIN

# Button byte: bit 5 = trigger pressed -------------------------------------
BUTTON_MASK = 0x20

# Commands (PC -> joystick) ------------------------------------------------
SET_CENTER = bytes((0xAA, 0x55, 0xAF, 0x00))
QUERY_POSITION = bytes((0xAA, 0x55, 0xAF, 0x01))
ACK = bytes((0xA5, 0x55, 0xAF))
CANCEL_ADDRESS = bytes((0xA5, 0x55, 0x05, 0x00, 0xFF))
_BAUD_CODES = {9600: 0x00, 19200: 0x01, 115200: 0x02}


def build_set_baud(baud: int) -> bytes:
    """Command that switches the joystick baud rate (answered by ACK)."""
    try:
        code = _BAUD_CODES[int(baud)]
    except KeyError:
        raise ValueError(
            f"unsupported joystick baud rate {baud!r}; "
            f"choose one of {sorted(_BAUD_CODES)}"
        ) from None
    return bytes((0xA5, 0x55, 0x01, code, 0xFF))


def build_set_address(address: int) -> bytes:
    """Command that puts the joystick into addressed bus mode."""
    if not 1 <= int(address) <= 64:
        raise ValueError("joystick address must be between 1 and 64")
    return bytes((0xA5, 0x55, 0x03, int(address), 0xFF))


def normalize_axis(raw: int) -> float:
    """Map a raw 12-bit axis value to ``-1.0 .. 1.0`` (centre plateau = 0).

    Values outside ``RAW_MIN..RAW_MAX`` are clamped, exactly like the original
    MATLAB/Python implementation.
    """
    value = max(RAW_MIN, min(int(raw), RAW_MAX))
    if value == RAW_CENTER:
        return 0.0
    if value < RAW_CENTER:
        return (value - RAW_MIN) / RAW_HALF_RANGE - 1.0
    return (value - (RAW_CENTER + 1)) / RAW_HALF_RANGE


@dataclass(frozen=True, slots=True)
class HallFrame:
    """One decoded joystick frame (raw values, as sent by the device).

    ``button`` is kept for protocol completeness/checksum validation; the
    paradigm itself is velocity-only and does not consume button events.
    """

    xx: int
    yy: int
    zz: int
    button: int
    address: int | None = None


class HallFrameParser:
    """Byte-stream state machine: resynchronising 9/10-byte frame parser.

    ``address is None`` selects the universal 9-byte frame; an integer selects
    the addressed 10-byte frame and validates the address byte.  A frame with
    a bad header/address/checksum is dropped and the parser slides one byte
    before searching for the next ``0xFF`` header, so a single corrupted or
    lost byte costs at most one frame.
    """

    def __init__(
        self,
        *,
        address: int | None = None,
        check_checksum: bool = True,
    ) -> None:
        if address is not None and not 1 <= int(address) <= 64:
            raise ValueError("joystick address must be between 1 and 64")
        self.address = None if address is None else int(address)
        self.check_checksum = bool(check_checksum)
        self.frame_len = (
            FRAME_LEN_UNIVERSAL if self.address is None else FRAME_LEN_ADDRESSED
        )
        self._buf = bytearray()
        self._in_frame = False
        self.frames = 0
        self.invalid = 0
        self.discarded = 0
        self.resyncs = 0

    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Forget partial data (port reopened or session restarted)."""
        self._buf.clear()
        self._in_frame = False

    def feed(self, data: bytes | bytearray) -> list[HallFrame]:
        """Consume serial bytes and return the frames completed by them."""
        self._buf.extend(data)
        frames: list[HallFrame] = []
        while True:
            if not self._in_frame:
                index = self._buf.find(HEADER)
                if index < 0:
                    self.discarded += len(self._buf)
                    self._buf.clear()
                    break
                if index:
                    self.discarded += index
                    del self._buf[:index]
                    self.resyncs += 1
                self._in_frame = True
            if len(self._buf) < self.frame_len:
                break
            frame = bytes(self._buf[: self.frame_len])
            parsed = self._parse(frame)
            if parsed is None:
                self.invalid += 1
                del self._buf[0]  # slide and look for the next header
                self._in_frame = False
            else:
                self.frames += 1
                frames.append(parsed)
                del self._buf[: self.frame_len]
                self._in_frame = False
        return frames

    # ------------------------------------------------------------------
    def _parse(self, frame: bytes) -> HallFrame | None:
        if len(frame) != self.frame_len or frame[0] != HEADER:
            return None
        if self.address is None:
            address = None
            yy = (frame[1] << 8) | frame[2]
            xx = (frame[3] << 8) | frame[4]
            zz = (frame[5] << 8) | frame[6]
            button = frame[7]
            checksum = frame[8]
            expected = (
                (xx >> 8)
                + (xx & 0xFF)
                + (yy >> 8)
                + (yy & 0xFF)
                + (zz >> 8)
                + (zz & 0xFF)
                + button
            ) & 0xFF
        else:
            address = frame[1]
            if address != self.address:
                return None
            yy = (frame[2] << 8) | frame[3]
            xx = (frame[4] << 8) | frame[5]
            zz = (frame[6] << 8) | frame[7]
            button = frame[8]
            checksum = frame[9]
            expected = (
                address
                + (xx >> 8)
                + (xx & 0xFF)
                + (yy >> 8)
                + (yy & 0xFF)
                + (zz >> 8)
                + (zz & 0xFF)
                + button
            ) & 0xFF
        if self.check_checksum and checksum != expected:
            return None
        return HallFrame(xx=xx, yy=yy, zz=zz, button=button, address=address)
