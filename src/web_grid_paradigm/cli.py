"""Command-line interface for the BCI web-grid paradigm."""

from __future__ import annotations

import argparse
import dataclasses
from pathlib import Path
from typing import Any

from loguru import logger

from . import __version__
from .config import ExperimentConfig
from .log import add_session_log, setup_logging
from .recorder import SessionRecorder

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
    logger.info("preview written to {}", written)
    return 0


def _run(config: ExperimentConfig, view: Any = None) -> dict[str, Any]:
    """Run one session; ``view`` receives live progress for the web panel."""
    import psychopy

    from .psychopy_runner import run_experiment

    recorder = SessionRecorder(config, psychopy_version=psychopy.__version__)
    sink_id = add_session_log(recorder.dir)
    try:
        logger.info(
            "subject={} session={} grid={}x{} blocks={} trials/block={} "
            "input={} selection={}",
            config.subject,
            recorder.session_id,
            config.rows,
            config.cols,
            config.blocks,
            config.targets,
            config.input,
            config.selection,
        )
        logger.info("saving to {}", recorder.dir)
        logger.debug("psychopy {} / config {}", psychopy.__version__, config.to_dict())
        if config.input == "udp":
            logger.info(
                "listening for BCI data on udp://{}:{}", config.udp_host, config.udp_port
            )
        if config.marker_udp:
            logger.info("UDP markers -> {}", config.marker_udp)
        if config.lsl:
            logger.info("LSL marker stream: {}", config.lsl_stream)
        return run_experiment(config, recorder, dashboard=view)
    finally:
        recorder.close()
        logger.remove(sink_id)


def _serve(config: ExperimentConfig, *, run_now: bool) -> int:
    """Start the web control panel and run whatever the page asks for."""
    from .station import start_station

    station = start_station(
        config.dashboard_host,
        config.dashboard_port,
        base_config=config,
        control=True,
        open_browser=config.dashboard_open,
    )
    if station is None:
        logger.warning("web panel unavailable; running once from the command line")
        _run(config)
        return 0
    logger.info("open {} and press 启动实验 (Ctrl+C quits)", station.url)
    try:
        if run_now:
            station.request_start(config, source="cli")
        station.serve(lambda cfg, view: _run(cfg, view))
    finally:
        station.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(debug=args.debug, log_file=args.log_file)
    logger.debug("webgrid {} started with argv={}", __version__, argv)
    try:
        config = _load_config(args)
    except Exception as exc:  # noqa: BLE001 - report any configuration problem
        logger.error("configuration error: {}", exc)
        return 2
    try:
        if args.screenshot is not None:
            return _preview(config, args.screenshot)
        if not config.dashboard:
            _run(config)
            return 0
        return _serve(config, run_now=args.run_now)
    except KeyboardInterrupt:
        logger.warning("interrupted")
        return 130
    except Exception as exc:  # noqa: BLE001 - top-level CLI error boundary
        if args.debug:
            logger.exception("error: {}", exc)
        else:
            logger.error("error: {}", exc)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
