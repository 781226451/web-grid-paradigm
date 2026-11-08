"""LSL outlets (event markers and live state) plus the liblsl log settings.

liblsl prints verbose INFO lines to the console unless configured; the bundled
``lsl_api.cfg`` keeps only errors.  LSLAPICFG must be set *before* ``pylsl`` is
imported, which is why the bootstrap lives at the top of this module and every
other module imports ``pylsl`` through here.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from loguru import logger

_LSL_CFG = Path(__file__).with_name("lsl_api.cfg")
if _LSL_CFG.exists():
    os.environ.setdefault("LSLAPICFG", str(_LSL_CFG))

import pylsl  # must follow the LSLAPICFG default above

__all__ = ["LslMarkerSink", "LslStateOutlet", "pylsl"]


def _info(stream_name: str, stream_type: str, fmt: str, source_id: str) -> Any:
    info = pylsl.StreamInfo(
        name=stream_name,
        type=stream_type,
        channel_count=1,
        nominal_srate=0,
        channel_format=fmt,
        source_id=source_id,
    )
    desc = info.desc()
    desc.append_child_value("manufacturer", "web-grid-paradigm")
    return info


class LslMarkerSink:
    """Numeric event-marker stream readable by LabRecorder / OpenViBE / MNE-LSL."""

    def __init__(self, stream_name: str) -> None:
        self._outlet = pylsl.StreamOutlet(_info(stream_name, "Markers", "int32", "webgrid-markers"))
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
        info = _info(stream_name, "WebGrid", "string", "webgrid-state")
        info.desc().append_child_value("content", "JSON paradigm state, 1 channel")
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
