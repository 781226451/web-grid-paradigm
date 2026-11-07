"""Command-line definition: options, defaults and config assembly.

The parser lives here so that :mod:`web_grid_paradigm.cli` stays a thin entry
point and other front-ends (the web panel) can reuse the same options.
"""

from __future__ import annotations

import argparse
import dataclasses
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from loguru import logger

from . import __version__
from .config import ExperimentConfig

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
  uv run webgrid --config configs/default.toml   # same, pre-filled
  uv run webgrid --run-now --input demo --targets 8 --auto-exit
  uv run webgrid --no-dashboard --input udp --lsl
  uv run webgrid --input udp --udp-port 9000 --marker-udp 127.0.0.1:9001
  uv run webgrid --screenshot docs/preview.png

The UDP input protocol and the data files are documented in README.md.
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
        "--config", type=Path, metavar="FILE", help="load parameters from TOML"
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
        choices=("mouse", "keyboard", "udp", "demo"),
        help="cursor/click source (default: mouse)",
    )
    inp.add_argument("--udp-host", help="UDP bind host (default: 127.0.0.1)")
    inp.add_argument("--udp-port", type=int, help="UDP bind port (default: 9000)")
    inp.add_argument(
        "--smoothing",
        type=float,
        metavar="0-0.95",
        help="exponential smoothing for UDP input",
    )
    inp.add_argument(
        "--keyboard-step", type=float, help="normalised step per arrow key"
    )
    inp.add_argument(
        "--demo-speed", type=float, help="autopilot speed (normalised units/s)"
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
    display.add_argument(
        "--show-cursor",
        action="store_true",
        default=None,
        help="show the operating-system cursor",
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
    display.add_argument(
        "--auto-exit",
        action="store_true",
        default=None,
        help="close automatically 2.5 s after the final screen",
    )

    markers = parser.add_argument_group("event markers")
    markers.add_argument(
        "--marker-udp", metavar="HOST:PORT", help="send JSON event markers over UDP"
    )
    markers.add_argument(
        "--lsl", action="store_true", default=None, help="publish an LSL marker stream"
    )
    markers.add_argument("--lsl-stream", help="LSL stream name")
    markers.add_argument(
        "--lsl-state",
        action="store_true",
        default=None,
        help="start the LSL state stream together with the web panel",
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
    reward.add_argument(
        "--reward-config",
        type=Path,
        metavar="FILE",
        help="TOML with hardware settings (reward_port, reward_baud, ...); "
        "defaults to configs/reward.toml when that file exists",
    )

    dash = parser.add_argument_group("web dashboard")
    dash.add_argument(
        "--no-dashboard",
        action="store_true",
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


def load_config(args: argparse.Namespace) -> ExperimentConfig:
    config = (
        ExperimentConfig.from_toml(args.config) if args.config else ExperimentConfig()
    )
    # Hardware settings live in their own file (per machine, not in git):
    # defaults <- --config <- reward TOML <- command line.
    reward_file = args.reward_config or default_reward_config()
    if reward_file is not None:
        config = apply_reward_config(config, reward_file)
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
        "udp_host": "udp_host",
        "udp_port": "udp_port",
        "smoothing": "smoothing",
        "keyboard_step": "keyboard_step",
        "demo_speed": "demo_speed",
        "window_width": "window_width",
        "window_height": "window_height",
        "screen": "screen",
        "marker_udp": "marker_udp",
        "lsl_stream": "lsl_stream",
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
    }
    for arg_name, field_name in fields.items():
        value = getattr(args, arg_name)
        if value is not None:
            overrides[field_name] = value
    if args.fullscreen:
        overrides["fullscreen"] = True
    if args.windowed:
        overrides["fullscreen"] = False
    if args.show_cursor:
        overrides["hide_cursor"] = False
    if args.no_instructions:
        overrides["skip_instructions"] = True
    if args.instructions:
        overrides["skip_instructions"] = False
    if args.auto_exit:
        overrides["auto_exit"] = True
    if args.lsl:
        overrides["lsl"] = True
    if args.lsl_state:
        overrides["lsl_state"] = True
    if args.no_dashboard:
        overrides["dashboard"] = False
    if args.open_dashboard:
        overrides["dashboard_open"] = True
    if args.no_open_dashboard:
        overrides["dashboard_open"] = False
    config = dataclasses.replace(config, **overrides)
    config.validate()
    return config


# ----------------------------------------------------------------------
# Reward hardware configuration (separate TOML, per machine)
# ----------------------------------------------------------------------
DEFAULT_REWARD_CONFIG = Path("configs/reward.toml")
REWARD_KEYS = (
    "reward",
    "reward_policy",
    "reward_ratio",
    "reward_port",
    "reward_baud",
    "reward_amount",
    "reward_duration_ms",
)


def default_reward_config() -> Path | None:
    """``configs/reward.toml`` when it exists (written once per setup machine)."""
    return DEFAULT_REWARD_CONFIG if DEFAULT_REWARD_CONFIG.is_file() else None


def apply_reward_config(
    config: ExperimentConfig, path: str | Path
) -> ExperimentConfig:
    """Layer the hardware settings from ``path`` over ``config``.

    The file may be flat or use a ``[reward]`` table; only reward keys are
    allowed, so a typo cannot silently change the paradigm.
    """
    path = Path(path)
    data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    table = data
    nested = data.get("reward")
    if isinstance(nested, Mapping):
        table = nested
    elif nested is not None and len(data) == 1:
        raise TypeError(f"{path}: 'reward' must be a string or a [reward] table")
    unknown = sorted(set(table) - set(REWARD_KEYS))
    if unknown:
        raise ValueError(f"{path}: unknown reward key(s): {', '.join(unknown)}")
    updated = dataclasses.replace(config, **dict(table))
    logger.info("reward hardware settings loaded from {}", path)
    return updated
