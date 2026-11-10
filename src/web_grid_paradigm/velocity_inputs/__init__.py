"""Input sources as interchangeable strategies.

A session uses exactly one :class:`~.base.VelocitySource`; the strategy is
selected by configuration and created by :func:`build_velocity_source`.  The
runner talks only to that interface, so device-specific code never leaks into
the render loop.

Every source reports movement through :class:`~.base.VelocityFrame`: velocity
sources fill ``samples`` with ``(timestamp, vx, vy)`` in normalised window
units per second and the cursor is derived by
:class:`~.integrator.VelocityIntegrator`; an absolute device (the mouse) fills
``position`` in the same normalised units and the facade applies it directly.
Optional button edges are returned in :attr:`~.base.VelocityFrame.clicks`, so
the paradigm keeps both click and dwell selection.  The strategies differ only
in how they obtain movement: the mouse reports the OS pointer position
directly, the serial joystick maps stick deflection to a velocity command, the
demo autopilot steers towards the target, and the LSL strategy reads the
velocity published by an external decoder.

Layout
------
``base``           interface, samples/frames, capabilities, optional protocols
``registry``       self-registration decorator + name -> strategy factory
``integrator``     velocity samples -> normalised cursor/pixel position
``mouse``          absolute OS pointer position + buttons
``demo``           deterministic autopilot for examples and smoke tests
``joystick``       serial hall-effect joystick (RS232/RS422/RS485)
``hall_protocol``  9/10-byte frame parser/checksum/axis normalisation
``lsl``            LSL velocity stream from the external decoder
"""

from __future__ import annotations

from .base import (
    ButtonStateProvider,
    DeviceContext,
    InitialPositionProvider,
    VelocityCapabilities,
    VelocityFrame,
    VelocitySample,
    VelocitySource,
    VelocitySourceError,
    VelocitySourceStatus,
    VelocitySourceUnavailable,
)
from .demo import DemoVelocityOptions, DemoVelocitySource
from .hall_protocol import (
    ACK,
    BUTTON_MASK,
    CANCEL_ADDRESS,
    HEADER,
    QUERY_POSITION,
    RAW_CENTER,
    RAW_HALF_RANGE,
    RAW_MAX,
    RAW_MIN,
    SET_CENTER,
    HallFrame,
    HallFrameParser,
    build_set_address,
    build_set_baud,
    normalize_axis,
)
from .integrator import VelocityIntegrator
from .joystick import (
    PROTOCOLS,
    SerialJoystickVelocityOptions,
    SerialJoystickVelocitySource,
)
from .lsl import LslVelocityOptions, LslVelocitySource
from .mouse import MouseVelocityOptions, MouseVelocitySource
from .registry import (
    available_velocity_sources,
    build_velocity_source,
    get_velocity_source_class,
    register_velocity_source,
)

__all__ = [
    "ACK",
    "BUTTON_MASK",
    "CANCEL_ADDRESS",
    "HEADER",
    "PROTOCOLS",
    "QUERY_POSITION",
    "RAW_CENTER",
    "RAW_HALF_RANGE",
    "RAW_MAX",
    "RAW_MIN",
    "SET_CENTER",
    "ButtonStateProvider",
    "DemoVelocityOptions",
    "DemoVelocitySource",
    "DeviceContext",
    "HallFrame",
    "HallFrameParser",
    "InitialPositionProvider",
    "LslVelocityOptions",
    "LslVelocitySource",
    "MouseVelocityOptions",
    "MouseVelocitySource",
    "SerialJoystickVelocityOptions",
    "SerialJoystickVelocitySource",
    "VelocityCapabilities",
    "VelocityFrame",
    "VelocityIntegrator",
    "VelocitySample",
    "VelocitySource",
    "VelocitySourceError",
    "VelocitySourceStatus",
    "VelocitySourceUnavailable",
    "available_velocity_sources",
    "build_set_address",
    "build_set_baud",
    "build_velocity_source",
    "get_velocity_source_class",
    "normalize_axis",
    "register_velocity_source",
]
