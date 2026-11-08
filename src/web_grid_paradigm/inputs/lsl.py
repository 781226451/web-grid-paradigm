"""LSL input strategy: the external decoder drives the cursor.

This is the *test* scenario: the BCI decoder (or an external controller)
publishes velocity samples over a Lab Streaming Layer inlet, and this strategy
turns them into :class:`~web_grid_paradigm.inputs.base.InputSample` objects.
The project already depends on ``pylsl`` for its marker/state outlets, so no
extra dependency is required.

Wire format (planned): one stream of ``channels`` floats, by default
``[timestamp, vx, vy]`` in normalised window units per second.  A zero or
missing timestamp means "stamp at receipt" on the runner clock.

Current state: options, class, capabilities and registry wiring only;
``open()`` raises :class:`~web_grid_paradigm.inputs.base.InputSourceUnavailable`
until the inlet transport lands in the next step.
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import (
    Capabilities,
    DeviceContext,
    InputRead,
    InputSourceUnavailable,
    SourceStatus,
)
from .registry import register_source


@dataclass(frozen=True, slots=True)
class LslOptions:
    """Configuration of the LSL input strategy."""

    stream_name: str = "WebGridVelocity"
    stream_type: str = "Velocity"
    resolve_timeout: float = 5.0
    stale_after: float = 1.0
    channels: int = 3


@register_source("lsl")
class LslInputSource:
    """Velocity samples from an LSL control stream (stub for now)."""

    name = "lsl"
    capabilities = Capabilities(category="lsl", continuous=True, absolute=False)

    def __init__(
        self,
        *,
        options: LslOptions | None = None,
        context: DeviceContext | None = None,
    ) -> None:
        self.options = options or LslOptions()
        self.context = context
        self._opened = False
        self._error: str | None = None

    # ------------------------------------------------------------------
    def open(self) -> None:
        raise InputSourceUnavailable(
            "LSL input strategy is not implemented yet: the "
            f"{self.options.stream_name!r} inlet transport lands in the "
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
                "stream": self.options.stream_name,
                "type": self.options.stream_type,
            },
            error=self._error,
        )
