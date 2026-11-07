"""Serial (USB/RS232/RS485) joystick strategy.

The lab joystick is a USB-serial peripheral, not an HID gamepad, so
``psychopy.hardware.joystick`` (pyglet/GLFW) cannot enumerate it.  This
strategy owns the serial transport and will host the device protocol state
machines:

* ``hzl_rs232_t1``     9600 baud, 9 bytes/frame, 28 Hz, start byte 0xFF,
                       XX/YY big-endian, raw range 48..976 (centre 512),
                       no button and no Z axis;
* ``hzl_rs485_t2``     115200 baud, 17 bytes/frame, button + XX/YY/ZZ;
* ``tyh45ag_modbus_t3`` 115200 baud, 13-byte Modbus RTU poll/reply.

Current state: options, class, capabilities, registry wiring and the
:class:`FrameParser` seam only.  ``open()`` raises
:class:`~web_grid_paradigm.inputs.base.InputSourceUnavailable` until the
protocol state machines land in the next step; the runner must not select
this strategy yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .base import (
    Capabilities,
    DeviceContext,
    InputRead,
    InputSourceUnavailable,
    SourceStatus,
)
from .registry import register_source

#: Protocol identifiers accepted by :class:`SerialJoystickOptions`.
PROTOCOLS = ("hzl_rs232_t1", "hzl_rs485_t2", "tyh45ag_modbus_t3")


@dataclass(frozen=True, slots=True)
class SerialJoystickOptions:
    """Configuration of the serial joystick strategy."""

    port: str = ""  # e.g. "/dev/cu.usbserial-XXXX" or "COM4"
    baud: int = 9600
    protocol: str = "hzl_rs232_t1"
    frame_len: int = 9
    expected_rate_hz: float = 28.0
    stale_after: float = 0.4  # seconds without data -> disconnected
    speed_px_per_s: float = 560.0  # full deflection, matching the old 20 px/frame @ 28 Hz
    invert_x: bool = False
    invert_y: bool = False
    read_timeout: float = 0.05


class FrameParser(Protocol):
    """Byte-stream framing state machine (implemented in the next step)."""

    def feed(self, data: bytes) -> list[bytes]:
        """Consume serial bytes and return the complete frames."""

    def reset(self) -> None:
        """Forget partial data (after an error or a port reopen)."""


@register_source("joystick")
class SerialJoystickSource:
    """Velocity samples from a serial-protocol joystick (stub for now)."""

    name = "joystick"
    capabilities = Capabilities(
        category="joystick",
        continuous=True,
        absolute=False,
        n_buttons=0,  # HZL type-1 has no button; type-2/3 report one
    )

    def __init__(
        self,
        *,
        options: SerialJoystickOptions | None = None,
        context: DeviceContext | None = None,
    ) -> None:
        self.options = options or SerialJoystickOptions()
        self.context = context
        self._opened = False
        self._error: str | None = None

    # ------------------------------------------------------------------
    def open(self) -> None:
        raise InputSourceUnavailable(
            "serial joystick strategy is not implemented yet: the "
            f"{self.options.protocol!r} frame state machine lands in the "
            "next step"
        )

    def close(self) -> None:
        self._opened = False

    def reset(self) -> None:
        return None

    def read(self, now: float) -> InputRead:
        return InputRead()

    # ------------------------------------------------------------------
    def status(self) -> SourceStatus:
        return SourceStatus(
            name=self.name,
            category=self.capabilities.category,
            connected=self._opened,
            device={
                "protocol": self.options.protocol,
                "port": self.options.port or "(unset)",
                "baud": str(self.options.baud),
            },
            frames=0,
            invalid=0,
            error=self._error,
        )
