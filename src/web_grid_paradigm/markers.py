"""Optional event-marker outputs (UDP and LSL) for EEG/BCI acquisition.

Markers are intentionally optional: a behavioural session must still run on a
laptop with no amplifier attached.  Choose ``--marker-udp host:port`` and/or
``--lsl``; every code below is sent with the label and, for UDP, the PsychoPy
monotonic timestamp.

The transports themselves live in :mod:`web_grid_paradigm.lsl` (LSL) and here
(UDP); this module defines the event codes and the fan-out policy.
"""

from __future__ import annotations

import json
import socket
from datetime import UTC, datetime
from typing import Any, Protocol

from loguru import logger

from .config import ExperimentConfig
from .lsl import LslMarkerSink

SESSION_START = 1
SESSION_END = 2
BLOCK_START = 3
BLOCK_END = 4
TARGET_ONSET = 10
HIT = 20
MISCLICK = 30
TIMEOUT = 40
SESSION_ABORT = 90

LABELS = {
    SESSION_START: "session_start",
    SESSION_END: "session_end",
    BLOCK_START: "block_start",
    BLOCK_END: "block_end",
    TARGET_ONSET: "target_onset",
    HIT: "hit",
    MISCLICK: "misclick",
    TIMEOUT: "timeout",
    SESSION_ABORT: "session_abort",
}


class MarkerSink(Protocol):
    def send(
        self, code: int, *, t: float | None = None, detail: dict[str, Any] | None = None
    ) -> None: ...

    def close(self) -> None: ...


class NullMarkerSink:
    def send(
        self, code: int, *, t: float | None = None, detail: dict[str, Any] | None = None
    ) -> None:
        return None

    def close(self) -> None:
        return None


class UdpMarkerSink:
    """One JSON datagram per marker, easy to ingest from MATLAB/Python."""

    def __init__(self, address: str) -> None:
        host, _, port = address.rpartition(":")
        if not host or not port.isdigit():
            raise ValueError(f"invalid marker UDP address: {address!r}")
        self.address = (host, int(port))
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(
        self, code: int, *, t: float | None = None, detail: dict[str, Any] | None = None
    ) -> None:
        payload = {
            "code": code,
            "event": LABELS.get(code, str(code)),
            "t": t,
            "utc": datetime.now(UTC).isoformat(),
            "detail": detail or {},
        }
        try:
            self._sock.sendto(json.dumps(payload).encode("utf-8"), self.address)
        except OSError as exc:  # pragma: no cover - network trouble
            logger.warning("could not send UDP marker: {}", exc)

    def close(self) -> None:
        self._sock.close()


class FanoutMarkerSink:
    def __init__(self, sinks: list[MarkerSink]) -> None:
        self.sinks = sinks

    def send(
        self, code: int, *, t: float | None = None, detail: dict[str, Any] | None = None
    ) -> None:
        for sink in self.sinks:
            sink.send(code, t=t, detail=detail)

    def close(self) -> None:
        for sink in self.sinks:
            sink.close()


def build_marker_sink(config: ExperimentConfig) -> MarkerSink:
    sinks: list[MarkerSink] = []
    if config.marker_udp:
        sinks.append(UdpMarkerSink(config.marker_udp))
    if config.lsl:
        sinks.append(LslMarkerSink(config.lsl_stream))
    if not sinks:
        return NullMarkerSink()
    return FanoutMarkerSink(sinks)
