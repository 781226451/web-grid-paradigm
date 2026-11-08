"""Strategy interface for external velocity sources.

The velocity input layer is a *strategy* family: a session holds exactly one
:class:`VelocitySource`; the concrete device (mouse, serial joystick, LSL
decoder) is selected by configuration and created through the registry and
factory in :mod:`web_grid_paradigm.velocity_inputs.registry`.  The runner only talks to
the interface below, so adding a device never touches the render loop.

Contract
--------
* A source emits **velocity samples** ``(timestamp, vx, vy)``.  The cursor
  position is derived by integrating them; a source never knows the window
  geometry, the current target, the trial state or the scoring rules.
* ``timestamp`` is on the runner's monotonic clock (``core.getTime()``), the
  same timebase as ``win.flip()`` and the session engine, in seconds.
* ``vx``/``vy`` are normalised window units per second: ``+x`` right, ``+y``
  up and ``1.0`` means half the window dimension per second.  The integrator
  (next step) converts them to pixels, so sources stay resolution independent.
* ``read(now)`` is called once per rendered frame.  It must not block and
  returns ``0..N`` velocity samples that arrived since the previous call.
  Device I/O stays outside the render loop.
* One instance per session; the strategy is chosen before the session starts
  and never swapped while a session is running.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..geometry import Layout


class VelocitySourceError(RuntimeError):
    """Base error for velocity-source problems (configuration or hardware)."""


class VelocitySourceUnavailable(VelocitySourceError):
    """The strategy is not implemented yet, or its device cannot be opened."""


@dataclass(frozen=True, slots=True)
class DeviceContext:
    """Everything a source may need from the running application.

    ``layout`` provides the pixel geometry used to convert device units to the
    normalised window coordinates of the interface.  ``window`` is a PsychoPy
    window and is only required by sources that read OS devices through
    PsychoPy (currently the mouse).
    """

    layout: Layout
    window: Any | None = None


@dataclass(frozen=True, slots=True)
class VelocitySample:
    """One velocity sample ``(timestamp, vx, vy)``."""

    timestamp: float
    vx: float
    vy: float


@dataclass(frozen=True, slots=True)
class VelocityFrame:
    """Everything a source produced for one frame.

    ``samples`` is ordered by ``timestamp``.
    """

    samples: tuple[VelocitySample, ...] = ()


@dataclass(frozen=True, slots=True)
class VelocityCapabilities:
    """Static description used for validation and user-facing hints."""

    category: str
    continuous: bool = True
    absolute: bool = False


@dataclass(frozen=True, slots=True)
class VelocitySourceStatus:
    """Snapshot for logging and the live web panel."""

    name: str
    category: str
    connected: bool = False
    device: dict[str, str] = field(default_factory=dict)
    last_rx: float | None = None
    latency_ms: float | None = None
    frames: int = 0
    invalid: int = 0
    dropped: int = 0
    stale: bool = False
    error: str | None = None


@runtime_checkable
class InitialPositionProvider(Protocol):
    """Optional capability: a source that knows its absolute cursor position.

    Only absolute devices (the mouse) implement it.  The integrator may call
    :meth:`initial_position_norm` once at session start so that the cursor
    begins where the physical pointer is instead of at the window centre.
    Velocity-only devices are assumed to start at the centre.
    """

    def initial_position_norm(self) -> tuple[float, float] | None: ...


@runtime_checkable
class VelocitySource(Protocol):
    """The strategy interface implemented by every input source."""

    name: str
    capabilities: VelocityCapabilities

    def open(self) -> None:
        """Open/connect the device.  May raise :class:`VelocitySourceError`."""

    def close(self) -> None:
        """Release the device.  Must be idempotent."""

    def read(self, now: float) -> VelocityFrame:
        """Return the velocity samples produced since the previous call."""

    def reset(self) -> None:
        """Forget per-block state (button edges, velocity baseline)."""

    def status(self) -> VelocitySourceStatus:
        """Return a snapshot for logging and the live panel."""
