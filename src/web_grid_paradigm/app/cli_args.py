"""Command-line definition: options, defaults and config assembly.

The parser lives here so that :mod:`web_grid_paradigm.app.cli` stays a thin entry
point and other front-ends (the web panel) can reuse the same options.
"""

from __future__ import annotations

import argparse
import dataclasses
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from loguru import logger

from .. import __version__
from ..core.config import ExperimentConfig, read_config_table
from ..core.settings import (
    DEFAULT_SOURCE,
    DEVICE_FIELDS,
    FIELD_SCOPES,
    SOURCE_CLI,
    SOURCE_CONFIG,
    SOURCE_DEVICE,
)

DESCRIPTION = """\
BCI Web-Grid: a PsychoPy target-selection paradigm.

By default `webgrid` opens a local web control panel: enter the parameters,
press 启动实验, and watch the session live in the browser.  Use --run-now to
start immediately with the command-line parameters, or --no-dashboard to run
without the panel.

A grid of cells is shown; one cell is highlighted.  Move the cursor onto it
and select it (click or dwell).  Hits add a target, misclicks subtract one,
and throughput is reported in bits per second (BPS).
"""

EPILOG = """\
The session starts as soon as you press 启动实验 in the web panel (or run with
--run-now); add --lsl to publish event markers over LSL.

examples:
  uv run webgrid                       # open the web panel, set params, start
  uv run webgrid --config configs/default.toml   # experiment + startup
  uv run webgrid --config configs/default.toml --device-config configs/velocity_input.toml
  uv run webgrid --run-now --input demo --targets 8 --auto-exit
  uv run webgrid --no-dashboard --input mouse --lsl
  uv run webgrid --input joystick --joystick-port COM4
  uv run webgrid --input lsl --lsl-velocity-stream WebGridVelocity
  uv run webgrid --screenshot docs/preview.png

The input sources and the data files are documented in README.md.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="webgrid",
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--config",
        type=Path,
        metavar="FILE",
        help="experiment and startup settings (flat TOML)",
    )
    parser.add_argument(
        "--device-config",
        dest="device_config",
        type=Path,
        action="append",
        metavar="FILE",
        help="device settings (flat TOML; repeat for several module files)",
    )
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="start the session immediately with these parameters instead of "
        "waiting for the web panel's 启动实验 button",
    )

    session = parser.add_argument_group("session")
    session.add_argument("--subject", help="subject label (default: sub-01)")
    session.add_argument("--session", help="session label (default: local timestamp)")
    session.add_argument("--language", choices=("zh", "en"), help="UI language")
    session.add_argument("--font", help="font family for all text")
    session.add_argument(
        "--output-dir", type=Path, metavar="DIR", help="data root (default: data)"
    )
    session.add_argument("--seed", type=int, help="target-sequence seed")

    grid = parser.add_argument_group("grid and task")
    grid.add_argument("--rows", type=int, help="grid rows (default: 12)")
    grid.add_argument("--cols", type=int, help="grid columns (default: 12)")
    grid.add_argument("--blocks", type=int, help="number of blocks (default: 1)")
    grid.add_argument(
        "--trials",
        "--targets",
        dest="targets",
        type=int,
        help="trials (targets) per block (default: 40)",
    )
    grid.add_argument(
        "--block-rest",
        type=float,
        metavar="S",
        help="blank rest between blocks in seconds (default: 10)",
    )
    grid.add_argument(
        "--max-seconds",
        type=float,
        help="optional per-block time limit (default: 300, 0 = off)",
    )
    grid.add_argument(
        "--selection", choices=("click", "dwell"), help="selection channel"
    )
    grid.add_argument(
        "--dwell-time", type=float, metavar="S", help="dwell duration in seconds"
    )
    grid.add_argument(
        "--trial-timeout",
        type=float,
        metavar="S",
        help="per-target timeout (0 disables)",
    )
    grid.add_argument(
        "--click-types",
        type=int,
        choices=(1, 2, 3),
        help="1-3 click types; target colour + required button",
    )
    grid.add_argument("--feedback", type=float, metavar="S", help="feedback interval")
    grid.add_argument(
        "--iti",
        type=float,
        metavar="S",
        help="inter-trial rest after feedback: empty grid, no target (default: 0)",
    )
    grid.add_argument(
        "--countdown-seconds", type=float, metavar="S", help="countdown duration"
    )

    inp = parser.add_argument_group("input")
    inp.add_argument(
        "--input",
        choices=("mouse", "demo", "joystick", "lsl"),
        help="cursor/click source (default: mouse)",
    )
    inp.add_argument(
        "--demo-speed", type=float, help="autopilot speed (normalised units/s)"
    )
    inp.add_argument(
        "--joystick-port",
        help="serial port of the hall-effect joystick (e.g. COM4)",
    )
    inp.add_argument("--joystick-baud", type=int, help="joystick baud rate (9600)")
    inp.add_argument(
        "--joystick-address",
        type=int,
        help="joystick bus address 1-64; 0 = universal 9-byte frame (default: 0)",
    )
    inp.add_argument(
        "--joystick-mode",
        dest="joystick_stream_mode",
        choices=("periodic", "on_change"),
        help="how the joystick sends frames (default: periodic)",
    )
    inp.add_argument(
        "--joystick-speed",
        type=float,
        help="joystick full-deflection speed in px/s (default: 560)",
    )
    inp.add_argument(
        "--joystick-deadzone",
        type=float,
        help="normalised joystick dead zone, 0-0.95 (default: 0)",
    )
    invert_x = inp.add_mutually_exclusive_group()
    invert_x.add_argument(
        "--joystick-invert-x",
        dest="joystick_invert_x",
        action="store_true",
        default=None,
        help="invert the joystick X axis",
    )
    invert_x.add_argument(
        "--no-joystick-invert-x",
        dest="joystick_invert_x",
        action="store_false",
        default=None,
        help="do not invert the joystick X axis",
    )
    invert_y = inp.add_mutually_exclusive_group()
    invert_y.add_argument(
        "--joystick-invert-y",
        dest="joystick_invert_y",
        action="store_true",
        default=None,
        help="invert the joystick Y axis",
    )
    invert_y.add_argument(
        "--no-joystick-invert-y",
        dest="joystick_invert_y",
        action="store_false",
        default=None,
        help="do not invert the joystick Y axis",
    )
    center = inp.add_mutually_exclusive_group()
    center.add_argument(
        "--joystick-center",
        dest="joystick_center",
        action="store_true",
        default=None,
        help="send the set-centre calibration command when the port opens",
    )
    center.add_argument(
        "--no-joystick-center",
        dest="joystick_center",
        action="store_false",
        default=None,
        help="do not send the set-centre command when the port opens",
    )
    inp.add_argument(
        "--joystick-stale-after",
        type=float,
        metavar="S",
        help="stop the cursor after S s without joystick frames (default: 0.4)",
    )
    inp.add_argument(
        "--lsl-velocity-stream",
        help="LSL stream name to match (default: WebGridVelocity)",
    )
    inp.add_argument(
        "--lsl-velocity-type",
        help="LSL stream type to match (default: Velocity)",
    )
    inp.add_argument(
        "--lsl-velocity-timeout",
        type=float,
        metavar="S",
        help="total LSL name+type resolve timeout in seconds (default: 5)",
    )
    inp.add_argument(
        "--lsl-velocity-stale-after",
        type=float,
        metavar="S",
        help="mark the LSL stream stale after S s without samples (default: 1)",
    )

    display = parser.add_argument_group("display")
    mode = display.add_mutually_exclusive_group()
    mode.add_argument(
        "--fullscreen",
        action="store_true",
        default=None,
        help="run fullscreen (default)",
    )
    mode.add_argument(
        "--windowed", action="store_true", default=None, help="force a window"
    )
    display.add_argument("--window-width", type=int, help="window width in pixels")
    display.add_argument("--window-height", type=int, help="window height in pixels")
    display.add_argument("--screen", type=int, help="monitor index")
    cursor = display.add_mutually_exclusive_group()
    cursor.add_argument(
        "--show-cursor",
        dest="hide_cursor",
        action="store_false",
        default=None,
        help="show the operating-system cursor",
    )
    cursor.add_argument(
        "--hide-cursor",
        dest="hide_cursor",
        action="store_true",
        default=None,
        help="hide the operating-system cursor (default)",
    )
    instruction_mode = display.add_mutually_exclusive_group()
    instruction_mode.add_argument(
        "--instructions",
        action="store_true",
        default=None,
        help="show the human instruction screen (off by default for animal use)",
    )
    instruction_mode.add_argument(
        "--no-instructions",
        action="store_true",
        default=None,
        help="skip the instruction screen (default)",
    )
    auto_exit = display.add_mutually_exclusive_group()
    auto_exit.add_argument(
        "--auto-exit",
        dest="auto_exit",
        action="store_true",
        default=None,
        help="close automatically 2.5 s after the final screen",
    )
    auto_exit.add_argument(
        "--no-auto-exit",
        dest="auto_exit",
        action="store_false",
        default=None,
        help="keep the final screen until the experimenter exits",
    )

    markers = parser.add_argument_group("event markers")
    lsl = markers.add_mutually_exclusive_group()
    lsl.add_argument(
        "--lsl", dest="lsl", action="store_true", default=None,
        help="publish an LSL marker stream",
    )
    lsl.add_argument(
        "--no-lsl",
        dest="lsl",
        action="store_false",
        default=None,
        help="do not publish an LSL marker stream",
    )
    markers.add_argument("--lsl-stream", help="LSL stream name")
    lsl_state = markers.add_mutually_exclusive_group()
    lsl_state.add_argument(
        "--lsl-state",
        dest="lsl_state",
        action="store_true",
        default=None,
        help="start the LSL state stream together with the web panel",
    )
    lsl_state.add_argument(
        "--no-lsl-state",
        dest="lsl_state",
        action="store_false",
        default=None,
        help="do not start the LSL state stream automatically",
    )
    markers.add_argument("--lsl-state-stream", help="LSL state stream name")
    markers.add_argument(
        "--lsl-state-rate", type=float, help="LSL state pushes per second (default 10)"
    )

    reward = parser.add_argument_group("reward")
    reward.add_argument(
        "--reward",
        choices=("serial", "test", "off"),
        help="reward strategy (default: serial); 'test' writes the bytes to "
        "reward_out.txt instead of a serial port",
    )
    reward.add_argument("--reward-port", help="serial port (default: COM3)")
    reward.add_argument(
        "--reward-policy",
        choices=("per_hit", "ratio", "none"),
        help="when to reward (default: per_hit): every hit, every N-th hit, "
        "or never",
    )
    reward.add_argument(
        "--reward-ratio", type=int, help="N for the 'ratio' policy (default: 2)"
    )
    reward.add_argument("--reward-baud", type=int, help="serial baud rate (default 9600)")
    reward.add_argument(
        "--reward-amount", type=int, help="reward units per hit (default: 1)"
    )
    reward.add_argument(
        "--reward-duration-ms", type=int, help="pulse length in ms (default: 50)"
    )

    dash = parser.add_argument_group("web dashboard")
    dash_mode = dash.add_mutually_exclusive_group()
    dash_mode.add_argument(
        "--dashboard",
        dest="dashboard",
        action="store_true",
        default=None,
        help="start the live web dashboard",
    )
    dash_mode.add_argument(
        "--no-dashboard",
        dest="dashboard",
        action="store_false",
        default=None,
        help="do not start the live web dashboard",
    )
    dash.add_argument(
        "--dashboard-port",
        type=int,
        help="dashboard port (default: 8765; 0 = pick a free port)",
    )
    dash.add_argument(
        "--dashboard-host",
        help="bind address (default: 127.0.0.1; 0.0.0.0 = allow other computers)",
    )
    dash.add_argument(
        "--open-dashboard",
        action="store_true",
        default=None,
        help="open the dashboard in the default browser",
    )
    dash.add_argument(
        "--no-open-dashboard",
        action="store_true",
        default=None,
        help="do not open a browser when the panel starts",
    )

    dev = parser.add_argument_group("developer")
    dev.add_argument(
        "--screenshot",
        type=Path,
        metavar="PNG",
        help="render one trial frame to a PNG and exit (no data are recorded)",
    )
    dev.add_argument(
        "--debug",
        action="store_true",
        help="debug mode: debug logs and full tracebacks",
    )
    dev.add_argument(
        "--log-file",
        type=Path,
        metavar="FILE",
        help="also write a rotating DEBUG log to FILE "
        "(each session always gets session.log in its data directory)",
    )
    return parser


@dataclasses.dataclass(frozen=True)
class ResolvedConfig:
    """A validated configuration plus the source of each field."""

    config: ExperimentConfig
    sources: dict[str, str]
    config_files: dict[str, str] = dataclasses.field(default_factory=dict)


def _default_sources() -> dict[str, str]:
    return {name: DEFAULT_SOURCE for name in FIELD_SCOPES}


def _reject_device_keys_in_config(
    path: str | Path, table: Mapping[str, Any]
) -> None:
    wrong = sorted(set(table) & DEVICE_FIELDS)
    if wrong:
        raise ValueError(
            f"{path}: {', '.join(wrong)} belong to device settings; "
            "move them to a --device-config file"
        )


def _reject_config_keys_in_device(
    path: str | Path, table: Mapping[str, Any]
) -> None:
    wrong = sorted(set(table) - DEVICE_FIELDS)
    if wrong:
        raise ValueError(
            f"{path}: only device keys are allowed in --device-config; "
            f"move {', '.join(wrong)} to the --config file"
        )


def load_config_resolved(args: argparse.Namespace) -> ResolvedConfig:
    """Load all configuration layers and retain the source of each field."""
    sources = _default_sources()
    config_files: dict[str, str] = {}
    config = ExperimentConfig()

    if args.config:
        table = read_config_table(args.config)
        _reject_device_keys_in_config(args.config, table)
        # Deliberately not validated yet: a valid --config may rely on values
        # from a device module (for example input = "joystick" with
        # joystick_port in a --device-config file).  The complete layer is
        # validated once all files and CLI overrides are merged.
        config = ExperimentConfig(**table)
        logger.info(
            "configuration file {}: {} key(s)", args.config, len(table)
        )
        logger.debug("configuration keys: {}", ", ".join(sorted(table)))
        for name in table:
            sources[name] = SOURCE_CONFIG

    owners: dict[str, Path] = {}
    for path in args.device_config or []:
        path = Path(path)
        table = read_config_table(path)
        _reject_config_keys_in_device(path, table)
        overlaps = sorted(set(table) & set(owners))
        if overlaps:
            files = sorted({str(owners[name]) for name in overlaps} | {str(path)})
            raise ValueError(
                f"{' and '.join(files)} both set {', '.join(overlaps)}; "
                "keep each key in exactly one device file"
            )
        for name in table:
            owners[name] = path
            sources[name] = SOURCE_DEVICE
            config_files[name] = str(path)
        config = dataclasses.replace(config, **table)
        logger.info("device configuration {}: {} key(s)", path, len(table))
        logger.debug(
            "device configuration keys {}: {}", path, ", ".join(sorted(table))
        )

    overrides: dict[str, Any] = {}
    fields = {
        "subject": "subject",
        "session": "session",
        "language": "language",
        "font": "font",
        "output_dir": "output_dir",
        "seed": "seed",
        "rows": "rows",
        "cols": "cols",
        "blocks": "blocks",
        "targets": "targets",
        "block_rest": "block_rest",
        "max_seconds": "max_seconds",
        "selection": "selection",
        "dwell_time": "dwell_time",
        "trial_timeout": "trial_timeout",
        "click_types": "click_types",
        "feedback": "feedback",
        "iti": "iti",
        "countdown_seconds": "countdown_seconds",
        "input": "input",
        "demo_speed": "demo_speed",
        "joystick_port": "joystick_port",
        "joystick_baud": "joystick_baud",
        "joystick_address": "joystick_address",
        "joystick_stream_mode": "joystick_stream_mode",
        "joystick_speed": "joystick_speed",
        "joystick_deadzone": "joystick_deadzone",
        "joystick_invert_x": "joystick_invert_x",
        "joystick_invert_y": "joystick_invert_y",
        "joystick_center": "joystick_center_on_open",
        "joystick_stale_after": "joystick_stale_after",
        "lsl_velocity_stream": "lsl_velocity_stream",
        "lsl_velocity_type": "lsl_velocity_type",
        "lsl_velocity_timeout": "lsl_velocity_timeout",
        "lsl_velocity_stale_after": "lsl_velocity_stale_after",
        "window_width": "window_width",
        "window_height": "window_height",
        "screen": "screen",
        "hide_cursor": "hide_cursor",
        "auto_exit": "auto_exit",
        "lsl": "lsl",
        "lsl_stream": "lsl_stream",
        "lsl_state": "lsl_state",
        "reward": "reward",
        "reward_policy": "reward_policy",
        "reward_ratio": "reward_ratio",
        "reward_port": "reward_port",
        "reward_baud": "reward_baud",
        "reward_amount": "reward_amount",
        "reward_duration_ms": "reward_duration_ms",
        "lsl_state_stream": "lsl_state_stream",
        "lsl_state_rate": "lsl_state_rate",
        "dashboard_port": "dashboard_port",
        "dashboard_host": "dashboard_host",
        "dashboard": "dashboard",
    }
    for arg_name, field_name in fields.items():
        value = getattr(args, arg_name)
        if value is not None:
            overrides[field_name] = value
    if args.fullscreen:
        overrides["fullscreen"] = True
    if args.windowed:
        overrides["fullscreen"] = False
    if args.no_instructions:
        overrides["skip_instructions"] = True
    if args.instructions:
        overrides["skip_instructions"] = False
    if args.open_dashboard:
        overrides["dashboard_open"] = True
    if args.no_open_dashboard:
        overrides["dashboard_open"] = False
    for field_name in overrides:
        sources[field_name] = SOURCE_CLI
        config_files.pop(field_name, None)
    config = dataclasses.replace(config, **overrides)
    config.validate()
    return ResolvedConfig(
        config=config, sources=sources, config_files=config_files
    )


def load_config(args: argparse.Namespace) -> ExperimentConfig:
    """Return only the resolved configuration (convenience helper)."""
    return load_config_resolved(args).config
