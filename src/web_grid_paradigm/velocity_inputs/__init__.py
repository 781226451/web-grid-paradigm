"""Velocity input sources as interchangeable strategies.

A session uses exactly one :class:`~.base.VelocitySource`; the strategy is
selected by configuration and created by :func:`build_velocity_source`.  The
runner talks only to that interface, so device-specific code never leaks into
the render loop.

Every source returns :class:`~.base.VelocitySample` objects
``(timestamp, vx, vy)`` in normalised window units per second; the cursor
position is derived by integrating them.  The strategies differ only in how
they obtain that velocity: the mouse differentiates absolute positions, the
serial joystick maps stick deflection to a velocity command, and the LSL
strategy reads the velocity published by an external decoder.

Layout
------
``base``           interface, velocity sample/frame dataclasses, capabilities
``registry``       self-registration decorator + name -> strategy factory
``mouse``          category 1: absolute OS pointer, differentiated to velocity
``joystick``       category 2: serial hall-effect joystick (RS232/RS422/RS485)
``hall_protocol``  9/10-byte frame parser/checksum/axis normalisation
``lsl``            category 3: LSL control stream from the external decoder (WIP)

The retired position-based UDP/autopilot input lives in
:mod:`web_grid_paradigm.legacy_inputs` until the runner is migrated.
"""

from __future__ import annotations

from .base import (
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
    # interface / data model
    "VelocityCapabilities",
    "DeviceContext",
    "InitialPositionProvider",
    "VelocityFrame",
    "VelocitySample",
    "VelocitySource",
    "VelocitySourceError",
    "VelocitySourceUnavailable",
    "VelocitySourceStatus",
    # registry / factory
    "available_velocity_sources",
    "build_velocity_source",
    "get_velocity_source_class",
    "register_velocity_source",
    # strategies
    "MouseVelocityOptions",
    "MouseVelocitySource",
    "PROTOCOLS",
    "SerialJoystickVelocityOptions",
    "SerialJoystickVelocitySource",
    "LslVelocitySource",
    "LslVelocityOptions",
    # serial joystick protocol
    "ACK",
    "BUTTON_MASK",
    "CANCEL_ADDRESS",
    "HEADER",
    "QUERY_POSITION",
    "RAW_CENTER",
    "RAW_HALF_RANGE",
    "RAW_MAX",
    "RAW_MIN",
    "SET_CENTER",
    "HallFrame",
    "HallFrameParser",
    "build_set_address",
    "build_set_baud",
    "normalize_axis",
]
