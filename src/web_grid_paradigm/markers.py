"""Optional event-marker outputs (UDP and LSL) for EEG/BCI acquisition.

Markers are intentionally optional: a behavioural session must still run on a
laptop with no amplifier attached.  Choose ``--marker-udp host:port`` and/or
``--lsl``; every code below is sent with the label and, for UDP, the PsychoPy
monotonic timestamp.
"""

from __future__ import annotations

import json
import logging
import socket
from datetime import UTC, datetime
from typing import Any, Protocol

from .config import ExperimentConfig

logger = logging.getLogger(__name__)

SESSION_START = 1
SESSION_END = 2
TARGET_ONSET = 10
HIT = 20
MISCLICK = 30
TIMEOUT = 40
SESSION_ABORT = 90

LABELS = {
    SESSION_START: "session_start",
    SESSION_END: "session_end",
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
            logger.warning("could not send UDP marker: %s", exc)

    def close(self) -> None:
        self._sock.close()


class LslMarkerSink:
    """Numeric marker stream readable by LabRecorder / OpenViBE / MNE-LSL."""

    def __init__(self, stream_name: str) -> None:
        try:
            from pylsl import StreamInfo, StreamOutlet
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "LSL markers need pylsl: run `uv sync --extra lsl`"
            ) from exc
        info = StreamInfo(
            name=stream_name,
            type="Markers",
            channel_count=1,
            nominal_srate=0,
            channel_format="cf_int32",
            source_id="webgrid-markers",
        )
        desc = info.desc()
        desc.append_child_value("manufacturer", "web-grid-paradigm")
        self._outlet = StreamOutlet(info)

    def send(
        self, code: int, *, t: float | None = None, detail: dict[str, Any] | None = None
    ) -> None:
        # LSL timestamps belong to the LSL clock, so let pylsl stamp locally
        # rather than passing PsychoPy's monotonic clock.
        self._outlet.push_sample([int(code)])

    def close(self) -> None:
        return None


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
