"""Command-line interface for the BCI web-grid paradigm."""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
import traceback
from pathlib import Path
from typing import Any

from . import __version__
from .config import ExperimentConfig
from .recorder import SessionRecorder

DESCRIPTION = """\
BCI Web-Grid: a PsychoPy target-selection paradigm.

A grid of cells is shown; one cell is highlighted.  Move the cursor onto it
and select it (click or dwell).  Hits add a target, misclicks subtract one,
and throughput is reported in bits per second (BPS).
"""

EPILOG = """\
examples:
  uv run webgrid --input demo --targets 8 --auto-exit
  uv run webgrid --input mouse --windowed
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
    grid.add_argument(
        "--targets", type=int, help="number of targets to present (default: 40)"
    )
    grid.add_argument(
        "--max-seconds",
        type=float,
        help="optional session time limit (default: 300, 0 = off)",
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

    dev = parser.add_argument_group("developer")
    dev.add_argument(
        "--screenshot",
        type=Path,
        metavar="PNG",
        help="render one trial frame to a PNG and exit (no data are recorded)",
    )
    dev.add_argument(
        "--debug", action="store_true", help="print tracebacks and debug logs"
    )
    return parser


def _load_config(args: argparse.Namespace) -> ExperimentConfig:
    config = (
        ExperimentConfig.from_toml(args.config) if args.config else ExperimentConfig()
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
        "targets": "targets",
        "max_seconds": "max_seconds",
        "selection": "selection",
        "dwell_time": "dwell_time",
        "trial_timeout": "trial_timeout",
        "click_types": "click_types",
        "feedback": "feedback",
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
    config = dataclasses.replace(config, **overrides)
    config.validate()
    return config


def _preview(config: ExperimentConfig, path: Path) -> int:
    from .markers import NullMarkerSink
    from .psychopy_runner import WebGridApp

    # A screenshot must not take over the experimenter's screen.
    preview_config = dataclasses.replace(config, fullscreen=False)
    app = WebGridApp(preview_config, recorder=None, marker_sink=NullMarkerSink())
    try:
        written = app.render_preview(path)
    finally:
        app.close()
    print(f"[webgrid] preview written to {written}")
    return 0


def _run(config: ExperimentConfig) -> int:
    import psychopy

    from .psychopy_runner import run_experiment

    recorder = SessionRecorder(config, psychopy_version=psychopy.__version__)
    print(
        f"[webgrid] subject={config.subject} session={recorder.session_id} "
        f"grid={config.rows}x{config.cols} targets={config.targets} "
        f"input={config.input} selection={config.selection}"
    )
    print(f"[webgrid] saving to {recorder.dir}")
    if config.input == "udp":
        print(
            f"[webgrid] listening for BCI data on udp://{config.udp_host}:{config.udp_port}"
        )
    if config.marker_udp:
        print(f"[webgrid] UDP markers -> {config.marker_udp}")
    if config.lsl:
        print(f"[webgrid] LSL marker stream: {config.lsl_stream}")
    try:
        run_experiment(config, recorder)
    finally:
        recorder.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        config = _load_config(args)
    except Exception as exc:  # noqa: BLE001 - report any configuration problem
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    try:
        if args.screenshot is not None:
            return _preview(config, args.screenshot)
        return _run(config)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 - top-level CLI error boundary
        if args.debug:
            traceback.print_exc()
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
