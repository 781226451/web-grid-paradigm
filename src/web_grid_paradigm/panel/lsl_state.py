"""LSL state stream publisher.

Runs in its own thread and pushes :meth:`Station.lsl_snapshot` at a fixed rate
while a session is running.  The outlet is created when the run starts and
closed when the end screen appears, so the stream never outlives a session.
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Any

from loguru import logger

from ..recording.lsl import LslStateOutlet

if TYPE_CHECKING:
    from .state import Station


class LslStatePublisher:
    """Background thread that pushes :meth:`Station.lsl_snapshot` over LSL."""

    def __init__(self, station: Station, stream_name: str, rate: float) -> None:
        self.station = station
        self.stream_name = stream_name
        self.rate = float(rate)
        self.outlet = LslStateOutlet(stream_name)
        self.sent = 0
        self.error: str | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._loop, name="webgrid-lsl-state", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def push_once(self, *, final: bool = False) -> None:
        self.outlet.push(self.station.lsl_snapshot(final=final))
        self.sent = self.outlet.sent

    def _loop(self) -> None:
        period = 1.0 / self.rate
        while not self._stop.wait(period):
            try:
                self.push_once()
                self.error = None
            except Exception as exc:  # noqa: BLE001 - keep publishing
                self.error = f"{type(exc).__name__}: {exc}"
                logger.warning("LSL state push failed: {}", exc)
                time.sleep(1.0)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "live": True,
            "stream": self.stream_name,
            "rate": self.rate,
            "sent": self.sent,
            "consumers": self.outlet.consumers(),
            "error": self.error,
        }

    def stop(self, *, final_sample: bool = False) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if final_sample:
            try:
                self.push_once(final=True)
            except Exception as exc:  # noqa: BLE001 - closing anyway
                logger.debug("final LSL state push failed: {}", exc)
        try:
            self.outlet.close()
        except Exception as exc:  # noqa: BLE001 - teardown must not fail
            logger.debug("could not close the LSL state outlet: {}", exc)
