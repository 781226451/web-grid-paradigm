"""Entry point: ``webgrid`` runs a session, optionally via the web panel.

The command-line options themselves live in :mod:`.cli_args`.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from loguru import logger

from .. import __version__
from ..core.config import ExperimentConfig
from ..recording.recorder import SessionRecorder
from .cli_args import build_parser, load_config
from .log import add_session_log, setup_logging


def _preview(config: ExperimentConfig, path: Path) -> int:
    from ..recording.markers import NullMarkerSink
    from .runner import WebGridApp

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

    from .runner import run_experiment

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
        if config.input == "joystick":
            logger.info(
                "joystick input on {} at {} baud (address={}, {})",
                config.joystick_port,
                config.joystick_baud,
                config.joystick_address or "universal",
                config.joystick_stream_mode,
            )
        elif config.input == "lsl":
            logger.info(
                "LSL velocity input: name={!r} type={!r}",
                config.lsl_velocity_stream,
                config.lsl_velocity_type,
            )
        if config.marker_udp:
            logger.info("UDP markers -> {}", config.marker_udp)
        if config.lsl:
            logger.info("LSL marker stream: {}", config.lsl_stream)
        return run_experiment(config, recorder, monitor=view)
    finally:
        recorder.close()
        logger.remove(sink_id)


def _serve(config: ExperimentConfig, *, run_now: bool) -> int:
    """Start the web control panel and run whatever the page asks for."""
    from ..panel import start_station

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
        config = load_config(args)
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
