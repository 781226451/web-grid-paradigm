"""Serial joystick strategy (HZL hall-effect joystick, RS232/RS422/RS485).

The lab joystick is a USB-serial peripheral, not an HID gamepad, so
``psychopy.hardware.joystick`` (pyglet/GLFW) cannot enumerate it.  This
strategy owns the serial transport and the 9/10-byte protocol state machine
(:mod:`web_grid_paradigm.velocity_inputs.hall_protocol`), and exposes the same
:class:`~web_grid_paradigm.velocity_inputs.base.VelocitySource` contract as the mouse and
the LSL strategies:

* the device reports the stick deflection; the source interprets it as a
  velocity command (``speed_px_per_s``) and emits one velocity sample per
  rendered frame from the latest device state, so motion stays smooth no
  matter whether the joystick uses *send-on-change* or *periodic* mode;
* the trigger bit (Button bit 5) is reported as click 1, so the paradigm can
  use click selection or dwell selection;
* the Z axis is decoded but unused by the 2-D paradigm.

A background reader thread owns the serial port, so the render loop only
drains a queue and never blocks.  The transport and the parser are injectable
for tests (``transport=...``, ``parser=...``, ``auto_thread=False``).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

from loguru import logger

from ..geometry import Layout
from .base import (
    DeviceContext,
    VelocityCapabilities,
    VelocityFrame,
    VelocitySample,
    VelocitySourceError,
    VelocitySourceStatus,
)
from .hall_protocol import (
    BUTTON_MASK,
    FRAME_LEN_ADDRESSED,
    FRAME_LEN_UNIVERSAL,
    SET_CENTER,
    HallFrame,
    HallFrameParser,
    normalize_axis,
)
from .registry import register_velocity_source

#: Protocol identifiers of the serial joystick strategy.
PROTOCOLS = ("hall_rs232",)
#: How the device pushes frames (see the protocol document).
STREAM_MODES = ("periodic", "on_change")


@dataclass(frozen=True, slots=True)
class SerialJoystickVelocityOptions:
    """Configuration of the serial joystick strategy."""

    port: str = ""  # e.g. "/dev/cu.usbserial-XXXX" or "COM4"
    baud: int = 9600  # universal protocol: 9600 8N1
    protocol: str = "hall_rs232"
    address: int | None = None  # None = universal 9-byte frame; 1..64 = bus mode
    stream_mode: str = "periodic"  # periodic | on_change
    stale_after: float = 0.4  # seconds without frames in periodic mode
    speed_px_per_s: float = 560.0  # full deflection, matches 20 px @ 28 Hz
    invert_x: bool = False
    invert_y: bool = False
    deadzone: float = 0.0  # normalised dead zone around the centre
    center_on_open: bool = False  # send the "set centre" calibration command
    read_timeout: float = 0.05
    max_queue: int = 256

    def __post_init__(self) -> None:
        if self.protocol not in PROTOCOLS:
            raise ValueError(
                f"unknown serial joystick protocol {self.protocol!r}; "
                f"choose one of {PROTOCOLS}"
            )
        if self.stream_mode not in STREAM_MODES:
            raise ValueError(
                f"unknown stream mode {self.stream_mode!r}; "
                f"choose one of {STREAM_MODES}"
            )
        if self.address is not None and not 1 <= int(self.address) <= 64:
            raise ValueError("joystick address must be between 1 and 64")
        if self.baud <= 0:
            raise ValueError("baud rate must be positive")
        if self.speed_px_per_s <= 0:
            raise ValueError("speed_px_per_s must be positive")
        if self.stale_after <= 0:
            raise ValueError("stale_after must be positive")
        if not 0.0 <= self.deadzone < 1.0:
            raise ValueError("deadzone must be in [0, 1)")
        if self.read_timeout <= 0:
            raise ValueError("read_timeout must be positive")
        if self.max_queue <= 0:
            raise ValueError("max_queue must be positive")


@register_velocity_source("joystick")
class SerialJoystickVelocitySource:
    """Velocity samples and trigger edges from the serial hall-effect joystick."""

    name = "joystick"
    capabilities = VelocityCapabilities(
        category="joystick",
        continuous=True,
        absolute=False,
        clicks=True,
    )

    def __init__(
        self,
        *,
        options: SerialJoystickVelocityOptions | None = None,
        context: DeviceContext | None = None,
        transport: Any | None = None,
        parser: HallFrameParser | None = None,
        auto_thread: bool = True,
    ) -> None:
        self.options = options or SerialJoystickVelocityOptions()
        self.context = context
        self._transport = transport
        self._parser = parser
        self._auto_thread = bool(auto_thread)

        # serial thread state
        self._lock = threading.Lock()
        self._io_lock = threading.Lock()
        self._queue: Any = None  # collections.deque, created in open()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

        # latest device state (updated by read(), consumed by the integrator)
        self._vx = 0.0
        self._vy = 0.0
        self._has_state = False
        self._clock_offset: float | None = None
        self._last_read_now: float | None = None
        self._last_rx: float | None = None
        self._opened_at: float | None = None

        # trigger edges (Button bit 5), reported as click 1
        self._prev_button = False
        self._pending_clicks: list[int] = []

        # counters / diagnostics
        self._opened = False
        self._connected = False
        self._frames = 0
        self._dropped = 0
        self._error: str | None = None

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    @property
    def layout(self) -> Layout:
        if self.context is None:
            raise VelocitySourceError("serial joystick needs a DeviceContext")
        return self.context.layout

    def open(self) -> None:
        if self._opened:
            if self._connected:
                return
            # The port failed at runtime; close it and try again below.
            self.close()
        if self.context is None:
            raise VelocitySourceError(
                "serial joystick needs a DeviceContext with the window layout"
            )
        self._parser = self._parser or HallFrameParser(address=self.options.address)
        self._parser.reset(counters=True)
        if self._transport is None:
            if not self.options.port:
                raise VelocitySourceError(
                    "serial joystick port is not configured "
                    "(set joystick_port to e.g. COM4)"
                )
            try:
                import serial  # lazy: pyserial is only needed by this strategy
            except ImportError as exc:  # pragma: no cover - dependency is declared
                raise VelocitySourceError(
                    "pyserial is required for the serial joystick strategy"
                ) from exc
            try:
                self._transport = serial.Serial(
                    self.options.port,
                    self.options.baud,
                    timeout=self.options.read_timeout,
                    write_timeout=self.options.read_timeout,
                )
            except Exception as exc:
                self._error = f"{type(exc).__name__}: {exc}"
                raise VelocitySourceError(
                    f"could not open joystick port {self.options.port!r} at "
                    f"{self.options.baud} baud: {exc}"
                ) from exc
        try:
            self._transport.reset_input_buffer()
        except Exception as exc:  # noqa: BLE001 - test transports may not implement it
            logger.debug("could not flush the joystick input buffer: {}", exc)

        from collections import deque

        self._queue = deque(maxlen=int(self.options.max_queue))
        self._frames = 0
        self._dropped = 0
        self._error = None
        self._clock_offset = None
        self._last_read_now = None
        self._last_rx = None
        self._opened_at = time.perf_counter()
        self._has_state = False
        self._vx = self._vy = 0.0
        self._prev_button = False
        self._pending_clicks.clear()
        self._stop.clear()
        self._opened = True
        self._connected = True

        if self.options.center_on_open:
            self._send(SET_CENTER)
        if self._auto_thread:
            self._thread = threading.Thread(
                target=self._reader_loop, name="webgrid-joystick", daemon=True
            )
            self._thread.start()

    def close(self) -> None:
        if not self._opened and self._transport is None:
            return
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)
        with self._io_lock:
            transport, self._transport = self._transport, None
            if transport is not None:
                try:
                    transport.close()
                except Exception as exc:  # noqa: BLE001 - teardown must not fail
                    logger.debug("could not close the joystick transport: {}", exc)
        self._opened = False
        self._connected = False
        self._has_state = False
        self._opened_at = None
        self._pending_clicks.clear()

    def reset(self) -> None:
        """Apply queued frames to the device state and forget the rest.

        Called at block boundaries: pending frames still update the internal
        deflection state, but no velocity sample or click is emitted for them.
        """
        if self._queue is None:
            return
        with self._lock:
            pending = list(self._queue)
            self._queue.clear()
        for perf_time, frame in pending:
            timestamp = (
                None if self._clock_offset is None else perf_time + self._clock_offset
            )
            self._apply_frame(frame, timestamp)
        self._pending_clicks.clear()

    # ------------------------------------------------------------------
    # device I/O (background thread) and per-frame drain
    # ------------------------------------------------------------------
    def pump(self) -> int:
        """Read the bytes that are currently available.

        Called by the reader thread; tests call it directly when
        ``auto_thread=False``.  Returns the number of bytes consumed.
        """
        if not self._opened:
            return 0
        with self._io_lock:
            transport = self._transport
            if transport is None:
                return 0
            try:
                data = transport.read(256)
            except Exception as exc:  # noqa: BLE001 - device unplugged etc.
                self._fail(exc)
                return 0
        if not data:
            return 0
        frames = self._parser.feed(data) if self._parser is not None else []
        if frames:
            received = time.perf_counter()
            with self._lock:
                for frame in frames:
                    if self._queue.maxlen and len(self._queue) >= self._queue.maxlen:
                        self._dropped += 1
                    self._queue.append((received, frame))
                self._frames += len(frames)
        return len(data)

    def _reader_loop(self) -> None:
        while not self._stop.is_set() and self._connected:
            self.pump()
            # pyserial's read() already waits up to read_timeout; the small
            # sleep only avoids spinning with transports that return at once.
            time.sleep(0.001)

    def read(self, now: float) -> VelocityFrame:
        """Drain new frames and return one velocity sample for this frame."""
        if not self._opened or self._queue is None:
            return VelocityFrame()
        perf_now = time.perf_counter()
        if self._clock_offset is None:
            self._clock_offset = now - perf_now
        with self._lock:
            pending = list(self._queue)
            self._queue.clear()
        for perf_time, frame in pending:
            self._apply_frame(frame, perf_time + self._clock_offset)
        self._last_read_now = now

        clicks = tuple(self._pending_clicks)
        self._pending_clicks.clear()
        samples: tuple[VelocitySample, ...] = ()
        if self._has_state and self._connected:
            if self._stale(now):
                samples = (VelocitySample(now, 0.0, 0.0),)
            else:
                samples = (VelocitySample(now, self._vx, self._vy),)
        return VelocityFrame(samples=samples, clicks=clicks)

    # ------------------------------------------------------------------
    def _stale(self, now: float) -> bool:
        """True when a periodic device stopped sending frames (watchdog)."""
        if self.options.stream_mode != "periodic" or not self._connected:
            return False
        if self._last_rx is not None:
            return (now - self._last_rx) > self.options.stale_after
        if self._opened_at is not None:
            return (time.perf_counter() - self._opened_at) > self.options.stale_after
        return False

    def _apply_frame(self, frame: HallFrame, timestamp: float | None) -> None:
        dx = normalize_axis(frame.xx)
        dy = normalize_axis(frame.yy)
        deadzone = self.options.deadzone
        if deadzone > 0.0:
            dx = 0.0 if abs(dx) < deadzone else dx
            dy = 0.0 if abs(dy) < deadzone else dy
        if self.options.invert_x:
            dx = -dx
        if self.options.invert_y:
            dy = -dy
        layout = self.layout
        # normalised units per second: 1.0 == half the window dimension / s
        self._vx = dx * self.options.speed_px_per_s * 2.0 / layout.window_w
        self._vy = dy * self.options.speed_px_per_s * 2.0 / layout.window_h
        self._has_state = True
        if timestamp is not None:
            self._last_rx = timestamp

        pressed = bool(frame.button & BUTTON_MASK)
        if pressed and not self._prev_button:
            self._pending_clicks.append(1)
        self._prev_button = pressed

    def _send(self, payload: bytes) -> None:
        with self._io_lock:
            transport = self._transport
            if transport is None:
                return
            try:
                transport.write(payload)
            except Exception as exc:  # noqa: BLE001 - calibration is best effort
                self._error = f"{type(exc).__name__}: {exc}"

    def _fail(self, exc: BaseException) -> None:
        self._connected = False
        self._has_state = False
        self._vx = self._vy = 0.0
        self._error = f"{type(exc).__name__}: {exc}"
        logger.warning("joystick I/O failed: {}", self._error)

    def button_pressed(self) -> bool:
        """True while the trigger is held (intro/exit screens)."""
        return bool(self._prev_button)

    # ------------------------------------------------------------------
    def status(self) -> VelocitySourceStatus:
        latency_ms: float | None = None
        if self._last_read_now is not None and self._last_rx is not None:
            latency_ms = max(0.0, (self._last_read_now - self._last_rx) * 1000.0)
        stale = False
        if self.options.stream_mode == "periodic" and self._connected:
            if self._last_read_now is not None and self._last_rx is not None:
                stale = (self._last_read_now - self._last_rx) > self.options.stale_after
            elif self._opened_at is not None:
                stale = (
                    time.perf_counter() - self._opened_at
                ) > self.options.stale_after
        return VelocitySourceStatus(
            name=self.name,
            category=self.capabilities.category,
            connected=self._connected,
            device={
                "protocol": self.options.protocol,
                "port": self.options.port or "(injected)",
                "baud": str(self.options.baud),
                "frame": (
                    str(FRAME_LEN_ADDRESSED)
                    if self.options.address is not None
                    else str(FRAME_LEN_UNIVERSAL)
                ),
                "stream": self.options.stream_mode,
            },
            last_rx=self._last_rx,
            latency_ms=latency_ms,
            frames=self._frames,
            invalid=self._parser.invalid if self._parser is not None else 0,
            dropped=self._dropped,
            stale=stale,
            error=self._error,
        )
