"""Cursor input sources for BCI and local testing.

Only the UDP source and the autopilot live here so that the protocol can be
tested without PsychoPy.  Mouse and keyboard handling stay in the renderer,
where PsychoPy's event objects are available.
"""

from __future__ import annotations

import json
import math
import socket
from dataclasses import dataclass
from typing import Any, Self

from loguru import logger


@dataclass(frozen=True, slots=True)
class InputState:
    x: float  # normalised window coordinate, -1..1, +x right
    y: float  # normalised window coordinate, -1..1, +y up
    clicks: tuple[int, ...] = ()  # buttons pressed since the previous poll


class UdpCursorSource:
    """Non-blocking UDP receiver for BCI decoder output.

    Each datagram is a JSON object::

        {"x": 0.12, "y": -0.30, "click": 0}

    ``x``/``y`` are window coordinates in [-1, 1] (origin at the centre,
    +y up).  A transition of ``click`` from 0 to 1/2/3 emits a button press.
    A sender may alternatively emit one-shot events::

        {"x": ..., "y": ..., "event": "click", "button": 1}

    Invalid datagrams are ignored and counted; they never stop the session.
    """

    MAX_PACKETS_PER_POLL = 256

    def __init__(
        self, host: str = "127.0.0.1", port: int = 9000, smoothing: float = 0.0
    ) -> None:
        self.host = host
        self.smoothing = float(smoothing)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((host, port))
        self._sock.setblocking(False)
        self.port = self._sock.getsockname()[1]
        logger.debug("UDP cursor source bound to {}:{}", host, self.port)
        self._x: float | None = None
        self._y: float | None = None
        self._held_button = 0
        self.invalid_packets = 0
        self.received_packets = 0
        self.last_packet_time: float | None = None
        self._warned = 0

    # ------------------------------------------------------------------
    def poll(self, now: float | None = None) -> InputState | None:
        clicks: list[int] = []
        got_position = False
        for _ in range(self.MAX_PACKETS_PER_POLL):
            try:
                payload, _addr = self._sock.recvfrom(65535)
            except BlockingIOError:
                break
            except OSError as exc:  # pragma: no cover - socket teardown
                logger.debug("UDP receive failed: {}", exc)
                break
            state = self._parse(payload, clicks)
            if state is not None:
                got_position = True
                self.received_packets += 1
                self.last_packet_time = now
        if not (got_position or clicks):
            return None
        return InputState(self._x or 0.0, self._y or 0.0, tuple(clicks))

    def _parse(self, payload: bytes, clicks: list[int]) -> tuple[float, float] | None:
        try:
            message = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._invalid()
            return None
        if not isinstance(message, dict):
            self._invalid()
            return None
        result = _decode_message(message)
        if result is None:
            self._invalid()
            return None
        x, y, held, event = result
        if self.smoothing > 0 and self._x is not None and self._y is not None:
            alpha = self.smoothing
            x = alpha * self._x + (1 - alpha) * x
            y = alpha * self._y + (1 - alpha) * y
        self._x, self._y = x, y
        if event is not None:
            if event not in clicks:
                clicks.append(event)
        elif held is not None:
            if held > 0 and held != self._held_button and held not in clicks:
                clicks.append(held)
            self._held_button = held
        return x, y

    def _invalid(self) -> None:
        self.invalid_packets += 1
        if self._warned < 5:
            self._warned += 1
            logger.warning(
                "ignored invalid BCI packet ({} so far)", self.invalid_packets
            )

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:  # pragma: no cover
            pass

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _decode_message(
    message: dict[str, Any],
) -> tuple[float, float, int | None, int | None] | None:
    try:
        x = float(message["x"])
        y = float(message["y"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    x = min(1.0, max(-1.0, x))
    y = min(1.0, max(-1.0, y))

    one_shot = message.get("event") == "click" or message.get("select") is True
    has_button = "button" in message or "click" in message
    raw_button = message.get("button", message.get("click", 0))
    try:
        button = int(raw_button)
    except (TypeError, ValueError):
        return None
    if button < 0:
        return None
    if one_shot:
        return x, y, None, (button or 1)
    return x, y, (button if has_button else None), None


class AutoPilot:
    """Deterministic cursor used by ``--input demo`` and smoke tests."""

    def __init__(
        self, speed: float = 2.2, start: tuple[float, float] = (0.0, 0.0)
    ) -> None:
        self.speed = float(speed)
        self.x, self.y = start
        self._target: tuple[float, float] | None = None
        self._clicked = False

    def poll(self, dt: float, target: tuple[float, float]) -> InputState:
        if target != self._target:
            self._target = target
            self._clicked = False
        dx = target[0] - self.x
        dy = target[1] - self.y
        distance = math.hypot(dx, dy)
        step = max(0.0, self.speed * dt)
        if distance <= max(step, 1e-6):
            self.x, self.y = target
            if not self._clicked:
                self._clicked = True
                return InputState(self.x, self.y, (1,))
            return InputState(self.x, self.y)
        self.x += dx / distance * step
        self.y += dy / distance * step
        return InputState(self.x, self.y)
