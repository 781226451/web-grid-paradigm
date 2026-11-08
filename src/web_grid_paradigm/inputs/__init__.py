"""Input sources as interchangeable strategies.

A session uses exactly one :class:`~.base.InputSource`; the strategy is
selected by configuration and created by :func:`build_input_source`.  The
runner talks only to the interface, so device-specific code never leaks into
the render loop.

Layout
------
``base``      interface, velocity-sample dataclasses, capabilities, status
``registry``  self-registration decorator + name -> strategy factory
``mouse``     category 1: absolute OS pointer, differentiated to velocity
``joystick``  category 2: serial hall-effect joystick (RS232/RS422/RS485)
``hall_protocol``  9/10-byte frame parser/checksum/axis normalisation
``lsl``       category 3: LSL control stream from the external decoder (WIP)
``legacy``    the previous UDP/autopilot module, kept importable while the
              runner is migrated to the strategy interface

``UdpCursorSource``, ``InputState`` and ``AutoPilot`` are re-exported from
:mod:`web_grid_paradigm.inputs.legacy` so existing imports keep working until
the runner switches to the new interface.
"""

from __future__ import annotations

from .base import (
    ButtonEvent,
    Capabilities,
    DeviceContext,
    InitialPositionProvider,
    InputRead,
    InputSample,
    InputSource,
    InputSourceError,
    InputSourceUnavailable,
    SourceStatus,
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
from .joystick import PROTOCOLS, SerialJoystickOptions, SerialJoystickSource
from .legacy import AutoPilot, InputState, UdpCursorSource
from .lsl import LslInputSource, LslOptions
from .mouse import MouseOptions, MouseSource
from .registry import (
    available_sources,
    build_input_source,
    get_source_class,
    register_source,
)

__all__ = [
    # interface / data model
    "ButtonEvent",
    "Capabilities",
    "DeviceContext",
    "InitialPositionProvider",
    "InputRead",
    "InputSample",
    "InputSource",
    "InputSourceError",
    "InputSourceUnavailable",
    "SourceStatus",
    # registry / factory
    "available_sources",
    "build_input_source",
    "get_source_class",
    "register_source",
    # strategies
    "MouseOptions",
    "MouseSource",
    "PROTOCOLS",
    "SerialJoystickOptions",
    "SerialJoystickSource",
    "LslInputSource",
    "LslOptions",
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
    # legacy compatibility
    "AutoPilot",
    "InputState",
    "UdpCursorSource",
]
