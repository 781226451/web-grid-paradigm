"""Optional LSL event-marker output for EEG/BCI acquisition.

Markers are intentionally optional: a behavioural session must still run on a
laptop with no amplifier attached.  Set ``lsl = true`` to publish every code
below with its label on the configured LSL marker stream.

The transport lives in :mod:`web_grid_paradigm.recording.lsl`; this module
defines the event codes and the sink policy.
"""

from __future__ import annotations

from typing import Any, Protocol

from ..core.config import ExperimentConfig
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


def build_marker_sink(config: ExperimentConfig) -> MarkerSink:
    if config.lsl:
        return LslMarkerSink(config.lsl_stream)
    return NullMarkerSink()
