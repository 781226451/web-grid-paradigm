"""The monitoring interface the renderer publishes to.

The core does not depend on the web panel: it only knows this protocol, which
``panel`` implements.  :class:`NullMonitor` is the "no panel" implementation.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SessionMonitor(Protocol):
    """Live state sink used by :class:`web_grid_paradigm.runner.WebGridApp`."""

    @property
    def stop_requested(self) -> bool:
        """True when the experimenter asked to abort from the panel."""

    @property
    def reward_sink(self) -> Any | None:
        """A reward device the panel already connected, if any."""

    def update(self, **fields: Any) -> None: ...

    def cursor(self, x_px: float, y_px: float, fps: float | None = None) -> None: ...

    def add_trial(self, row: dict[str, Any]) -> None: ...

    def set_blocks(self, blocks: list[dict[str, Any]]) -> None: ...

    def close(self) -> None: ...


class NullMonitor:
    """Monitoring disabled: accepts everything, publishes nothing."""

    stop_requested = False
    reward_sink = None

    def update(self, **fields: Any) -> None:
        return None

    def cursor(self, x_px: float, y_px: float, fps: float | None = None) -> None:
        return None

    def add_trial(self, row: dict[str, Any]) -> None:
        return None

    def set_blocks(self, blocks: list[dict[str, Any]]) -> None:
        return None

    def close(self) -> None:
        return None
