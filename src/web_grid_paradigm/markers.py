"""Optional event-marker outputs (UDP and LSL) for EEG/BCI acquisition.

Markers are intentionally optional: a behavioural session must still run on a
laptop with no amplifier attached.  Choose ``--marker-udp host:port`` and/or
``--lsl``; every code below is sent with the label and, for UDP, the PsychoPy
monotonic timestamp.
"""

from __future__ import annotations

import json
import os
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from loguru import logger

from .config import ExperimentConfig

# liblsl prints verbose INFO lines to the console unless configured; ship a
# config that keeps only errors.  An explicit LSLAPICFG still wins.
_LSL_CFG = Path(__file__).with_name("lsl_api.cfg")
if _LSL_CFG.exists():
    os.environ.setdefault("LSLAPICFG", str(_LSL_CFG))

import pylsl  # must follow the LSLAPICFG default above

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


class LslMarkerSink:
    """Numeric marker stream readable by LabRecorder / OpenViBE / MNE-LSL."""

    def __init__(self, stream_name: str) -> None:
        info = pylsl.StreamInfo(
            name=stream_name,
            type="Markers",
            channel_count=1,
            nominal_srate=0,
            channel_format="int32",
            source_id="webgrid-markers",
        )
        desc = info.desc()
        desc.append_child_value("manufacturer", "web-grid-paradigm")
        self._outlet = pylsl.StreamOutlet(info)
        logger.debug("LSL marker outlet {!r} created", stream_name)

    def send(
        self, code: int, *, t: float | None = None, detail: dict[str, Any] | None = None
    ) -> None:
        # LSL timestamps belong to the LSL clock, so let pylsl stamp locally
        # rather than passing PsychoPy's monotonic clock.
        self._outlet.push_sample([int(code)])

    def close(self) -> None:
        return None


class LslStateOutlet:
    """JSON state stream: one string channel per snapshot.

    Unlike the integer event markers, this stream reports the *current* state
    (phase, block/trial progress, target cell, scores) so any LSL client can
    follow the paradigm without decoding event codes.
    """

    def __init__(self, stream_name: str = "WebGridState") -> None:
        info = pylsl.StreamInfo(
            name=stream_name,
            type="WebGrid",
            channel_count=1,
            nominal_srate=0,
            channel_format="string",
            source_id="webgrid-state",
        )
        desc = info.desc()
        desc.append_child_value("manufacturer", "web-grid-paradigm")
        desc.append_child_value("content", "JSON paradigm state, 1 channel")
        self._outlet = pylsl.StreamOutlet(info)
        self.stream_name = stream_name
        self.sent = 0
        logger.info("LSL state stream {!r} started", stream_name)

    def push(self, payload: dict[str, Any]) -> None:
        self._outlet.push_sample([json.dumps(payload, ensure_ascii=False, default=str)])
        self.sent += 1

    def consumers(self) -> int:
        try:
            return int(self._outlet.have_consumers())
        except Exception:  # noqa: BLE001 - liblsl quirk, not worth failing over
            return 0

    def close(self) -> None:
        logger.info("LSL state stream {!r} stopped", self.stream_name)
        self._outlet = None  # type: ignore[assignment]


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
