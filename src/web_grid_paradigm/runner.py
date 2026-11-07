"""Session runner: window lifetime, block flow and the render loop.

This module orchestrates; it does not know how to draw a frame
(:mod:`renderer`), read a device (:mod:`input_router`), write data
(:mod:`reporter`) or decide when a trial ends (:mod:`session`).
"""

from __future__ import annotations

import platform
import random
import time
from pathlib import Path
from typing import Any

import psychopy
from loguru import logger
from psychopy import core, event

from .config import ExperimentConfig
from .geometry import Cell, Layout
from .i18n import Strings
from .input_router import InputReader
from .markers import MarkerSink, build_marker_sink
from .monitor import NullMonitor, SessionMonitor
from .renderer import Renderer
from .reporter import Reporter
from .reward.policy import build_reward_policy
from .scoring import SessionStats, merge_stats
from .session import FrameOutcome, Phase, SessionEngine, Target
from .stimuli import Stimuli
from .window import create_window

UI_SCALE_RANGE = (0.65, 2.2)
REFERENCE_SIZE = (1280, 800)
AUTO_EXIT_DELAY_S = 2.5


class WebGridApp:
    """Owns the window, stimuli, input devices and the block/trial flow."""

    PUBLISH_INTERVAL = 1 / 30  # live-monitor updates sent at most 30 Hz

    def __init__(
        self,
        config: ExperimentConfig,
        recorder: Any | None = None,
        marker_sink: MarkerSink | None = None,
        monitor: SessionMonitor | None = None,
    ) -> None:
        self.cfg = config
        self.rec = recorder
        self.monitor = monitor or NullMonitor()
        self.strings = Strings(config.language)

        self.win = create_window(config)
        width, height = (int(v) for v in self.win.size)
        try:
            self.layout = Layout.create(width, height, config.rows, config.cols)
        except BaseException:
            self.win.close()
            raise
        self.ui = max(
            UI_SCALE_RANGE[0],
            min(
                UI_SCALE_RANGE[1],
                min(width / REFERENCE_SIZE[0], height / REFERENCE_SIZE[1]),
            ),
        )

        self.stimuli = Stimuli(
            self.win, self.layout, self.ui, config.font, self.strings
        )
        self.stimuli.configure_intro_texts(config)
        self.renderer = Renderer(self.win, self.layout, self.stimuli)
        self.input = InputReader(self.win, self.layout, config)
        # A device connected from the web panel is shared by every session; it
        # is only used in serial mode (test/off keep their own behaviour).
        panel_device = (
            getattr(self.monitor, "reward_sink", None)
            if config.reward == "serial"
            else None
        )
        self.reporter = Reporter(
            config,
            self.layout,
            recorder=recorder,
            marker_sink=marker_sink,
            monitor=self.monitor,
            reward_sink=panel_device,
            own_reward_sink=False,
        )
        # "When to reward" is a strategy of its own, independent of how the
        # pulse is delivered (serial / test / off).
        self.reward_policy = build_reward_policy(config)

        # One engine per block; the shared RNG keeps blocks reproducible but
        # gives each block a different target sequence.
        self._rng = random.Random(config.seed)
        self.block = 1
        self.engine = SessionEngine(config, self.layout, self._rng)
        self._block_results: list[dict[str, Any]] = []
        self._block_stats: list[tuple[SessionStats, float]] = []
        self._block_closed = False
        self._rest_until = 0.0
        self._set_recorder_block()

        self.state = "intro"  # intro | countdown | run | rest | done
        self._last_frame = core.getTime()
        self._done_at = 0.0
        self._exit = False
        self._closed = False
        self._finalized = False
        self._summary: dict[str, Any] = {}

        self._pending_target_onset = False
        self._pending_feedback_start = False
        self._fps = 0.0
        self._next_publish = 0.0
        self.countdown_start = 0.0

        self.reporter.session_open(
            self._last_frame,
            psychopy_version=psychopy.__version__,
            python_version=platform.python_version(),
        )
        if config.skip_instructions:
            self._begin_countdown(core.getTime())

    # ------------------------------------------------------------------
    # public entry points
    # ------------------------------------------------------------------
    def run(self) -> None:
        try:
            self._loop()
        except BaseException:
            try:
                self._finalize(core.getTime(), aborted=True)
            except Exception:  # noqa: BLE001  # pragma: no cover - never mask the original error
                logger.exception("could not write the abort summary")
            raise
        finally:
            self._cleanup()

    def render_preview(self, path: str | Path) -> Path:
        """Render one representative trial frame (used for docs/visual QC)."""
        now = core.getTime()
        self.state = "run"
        cell = Cell(self.cfg.rows // 2, min(self.cfg.cols - 1, self.cfg.cols // 2 + 1))
        self.engine.target = Target(
            index=15,
            cell=cell,
            required_button=min(self.cfg.click_types, 3),
            onset=now - 1.3,
            start_px=(0.0, 0.0),
            centre_px=self.layout.centre_px(cell),
        )
        self.engine.phase = Phase.RUNNING
        centre = self.layout.centre_px(cell)
        self.input.cursor_px = (
            centre[0] - self.layout.cell * 0.45,
            centre[1] - self.layout.cell * 0.1,
        )
        self.renderer.draw_run(now, self.engine, self.input.cursor_px)
        self.win.flip()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.win.getMovieFrame()
        self.win.saveMovieFrames(str(path))
        return path

    def close(self) -> None:
        self._cleanup()

    @property
    def summary(self) -> dict[str, Any]:
        return dict(self._summary)

    # ------------------------------------------------------------------
    # main loop
    # ------------------------------------------------------------------
    def _loop(self) -> None:
        self._last_frame = core.getTime()
        while not self._exit:
            now = core.getTime()
            dt = min(0.1, max(0.0, now - self._last_frame))
            self._last_frame = now
            self._publish(now, dt)
            keys = event.getKeys()

            if "escape" in keys or self.monitor.stop_requested:
                self._handle_stop(now, keys)
                break

            if self.state == "intro":
                if self.input.start_requested(now, keys):
                    self._begin_countdown(now)
                else:
                    self.renderer.draw_intro()
                    self.win.flip()
                    continue

            if self.state == "countdown":
                if now - self.countdown_start >= self.cfg.countdown_seconds:
                    self._begin_run(now)
                else:
                    self.input.poll_cursor(now)
                    self.renderer.draw_countdown()
                    self.win.flip()
                    continue

            if self.state == "rest":
                if now >= self._rest_until:
                    self._next_block(now)
                else:
                    self.input.poll_cursor(now)
                    self.renderer.draw_rest()
                    self.win.flip()
                    continue

            if self.state == "run":
                self._run_frame(now, dt, keys)
            elif self.state == "done":
                self.renderer.draw_done()
                self.win.flip()
                if self._exit_requested(now, keys):
                    self._exit = True

    def _handle_stop(self, now: float, keys: list[str]) -> None:
        if self.monitor.stop_requested:
            logger.warning("stop requested from the web panel; ending session")
        else:
            logger.warning("escape pressed during '{}'; ending session", self.state)
        if self.state in ("run", "countdown", "intro", "rest"):
            self._finalize(now, aborted=True)
        self._exit = True

    def _exit_requested(self, now: float, keys: list[str]) -> bool:
        """Leaving the blank end screen (auto-exit, space/return or a click)."""
        return (
            (self.cfg.auto_exit and now - self._done_at >= AUTO_EXIT_DELAY_S)
            or "space" in keys
            or "return" in keys
            or any(self.input.mouse.getPressed())
        )

    # ------------------------------------------------------------------
    # block flow
    # ------------------------------------------------------------------
    def _begin_countdown(self, now: float) -> None:
        self.state = "countdown"
        self.countdown_start = now
        logger.info(
            "block {}/{}: countdown started ({} s)",
            self.block,
            self.cfg.blocks,
            self.cfg.countdown_seconds,
        )
        if self.block == 1:
            self.reporter.instructions_end(
                now, skipped=self.cfg.skip_instructions
            )
        self.reporter.countdown_start(now)
        if self.cfg.countdown_seconds <= 0:
            self._begin_run(now)

    def _begin_run(self, now: float) -> None:
        self.state = "run"
        self._pending_target_onset = True
        self._pending_feedback_start = False
        self.renderer.reset()
        self.input.reset_buttons()
        self.engine.begin(now, *self.input.cursor_px)
        self._block_closed = False
        logger.info(
            "block {}/{} started: {} trials on a {}x{} grid",
            self.block,
            self.cfg.blocks,
            self.cfg.targets,
            self.cfg.rows,
            self.cfg.cols,
        )
        self.reporter.run_start(now, self.block)
        self.reporter.block_start(now, self.block)

    def _close_block(self, now: float, *, aborted: bool) -> None:
        """Record the current block's results once."""
        if self._block_closed or self.engine.session_start is None:
            return
        self._block_closed = True
        if aborted:
            self.engine.abort(now)
        result = self.engine.summary(now)
        result["block"] = self.block
        self._block_results.append(result)
        self._block_stats.append((self.engine.stats, result["duration_s"]))
        self.monitor.set_blocks(self._block_results)
        logger.info(
            "block {}/{} {}: attempts={} hits={} misclicks={} bps={:.3f}",
            self.block,
            self.cfg.blocks,
            "aborted" if aborted else "finished",
            result["attempts"],
            result["hits"],
            result["misclicks"],
            result["bps"],
        )
        self.reporter.block_end(now, self.block, result, aborted=aborted)

    def _end_block(self, now: float) -> None:
        self._close_block(now, aborted=False)
        if self.block >= self.cfg.blocks:
            self._finalize(now, aborted=False)
            return
        self.state = "rest"
        self._rest_until = now + self.cfg.block_rest
        logger.info("rest {} s before block {}", self.cfg.block_rest, self.block + 1)
        self.reporter.rest_start(now)

    def _next_block(self, now: float) -> None:
        self.block += 1
        previous = self.engine.target.cell if self.engine.target else None
        self.engine = SessionEngine(
            self.cfg, self.layout, self._rng, avoid_first=previous
        )
        self.input.restart_autopilot()
        self._set_recorder_block()
        self._begin_countdown(now)

    def _set_recorder_block(self) -> None:
        if self.rec is not None:
            self.rec.block = self.block

    # ------------------------------------------------------------------
    # frames
    # ------------------------------------------------------------------
    def _run_frame(self, now: float, dt: float, keys: list[str]) -> None:
        if self.engine.phase is Phase.DONE:
            self._end_block(now)
            self.win.flip()
            return

        if self._trial_boundary_reached(now):
            target = self.engine.advance(now, *self.input.cursor_px)
            if self.engine.phase is Phase.DONE:
                self._end_block(now)
                self.win.flip()
                return
            if self.engine.phase is Phase.ITI:
                self._log_iti_start(now)
            if target is not None:
                self._pending_target_onset = True

        if self.engine.phase is Phase.RUNNING and not self._pending_target_onset:
            x, y, clicks = self.input.read(now, dt, keys, self.engine.target)
            self._handle_outcome(self.engine.update(now, x, y, clicks))
        elif self.engine.phase in (Phase.FEEDBACK, Phase.ITI):
            # Keep the devices fresh during feedback/ITI (especially the mouse
            # button edges) but discard any click.
            self.input.read(now, dt, keys, self.engine.target)

        self.renderer.draw_run(now, self.engine, self.input.cursor_px)
        flip_time = self.win.flip()

        if self._pending_target_onset:
            self._mark_target_onset(flip_time)
            self._pending_target_onset = False
        if self._pending_feedback_start:
            self.engine.feedback_until = flip_time + self.cfg.feedback
            self._pending_feedback_start = False

    def _trial_boundary_reached(self, now: float) -> bool:
        engine = self.engine
        if (
            engine.phase is Phase.FEEDBACK
            and not self._pending_feedback_start
            and now >= engine.feedback_until
        ):
            return True
        return engine.phase is Phase.ITI and now >= engine.iti_until

    def _handle_outcome(self, outcome: FrameOutcome) -> None:
        for click in outcome.clicks:
            misclick = self.reporter.click(click, target=self.engine.target)
            if misclick:
                self.renderer.flash_miss(click.cell, click.time)
        if outcome.trial is not None:
            self.reporter.trial(outcome.trial, block=self.block)
            decision = self.reward_policy.on_trial(
                outcome.trial, block=self.block, config=self.cfg
            )
            if decision is not None:
                self.reporter.reward(
                    outcome.trial.offset,
                    amount=decision.amount,
                    duration_ms=decision.duration_ms,
                    reason=decision.reason,
                    trial_index=outcome.trial.index,
                )
            self._pending_feedback_start = True

    def _log_iti_start(self, now: float) -> None:
        logger.debug(
            "block {} ITI {} s after trial {}",
            self.block,
            self.cfg.iti,
            self.engine.stats.attempts,
        )
        self.reporter.iti_start(now, trial_index=self.engine.stats.attempts)

    def _mark_target_onset(self, flip_time: float) -> None:
        target = self.engine.target
        if target is None:
            return
        self.engine.retime_onset(flip_time)
        logger.debug(
            "block {} target {} onset cell={} button={} t={:.4f}",
            self.block,
            target.index,
            target.cell.label,
            target.required_button,
            flip_time,
        )
        self.reporter.target_onset(
            flip_time,
            block=self.block,
            target=target,
            cursor_px=self.input.cursor_px,
        )

    # ------------------------------------------------------------------
    # live monitor
    # ------------------------------------------------------------------
    def _publish(self, now: float, dt: float) -> None:
        """Push the current state to the panel (cheap; rate limited)."""
        if dt > 0:
            self._fps = 0.9 * self._fps + 0.1 / dt if self._fps else 1 / dt
        if now < self._next_publish:
            return
        self._next_publish = now + self.PUBLISH_INTERVAL
        engine = self.engine
        phase = self.state
        if phase == "run":
            if engine.phase is Phase.FEEDBACK:
                phase = "feedback"
            elif engine.phase is Phase.ITI:
                phase = "iti"
        target = engine.target
        target_info = (
            {
                "row": target.cell.row,
                "col": target.cell.col,
                "label": target.cell.label,
                "button": target.required_button,
                "index": target.index,
            }
            if target is not None and phase in ("run", "feedback", "iti")
            else None
        )
        block_elapsed = (
            engine.elapsed(now) if engine.session_start is not None else None
        )
        flash_until = self.renderer.cursor_flash_until
        self.monitor.update(
            phase=phase,
            block=self.block,
            trials_done=engine.stats.attempts,
            target=target_info,
            dwell_progress=round(engine.dwell_progress, 3),
            block_elapsed=(
                round(block_elapsed, 2) if block_elapsed is not None else None
            ),
            block_bps=(
                round(engine.summary(now)["bps"], 3)
                if engine.stats.attempts
                else None
            ),
            flash_until=(
                time.time() + (flash_until - now) if flash_until > now else None
            ),
            aborted=engine.aborted and self.state == "done",
        )
        self.monitor.cursor(*self.input.cursor_px, fps=self._fps)

    # ------------------------------------------------------------------
    # finalisation
    # ------------------------------------------------------------------
    def _finalize(self, now: float, aborted: bool) -> None:
        if self._finalized:
            return
        self._finalized = True
        # An abort mid-block records the partial block; aborting during the
        # countdown before a block starts records nothing for it.
        self._close_block(now, aborted=aborted)
        summary = merge_stats(
            self._block_stats, self.cfg.n_cells, self.cfg.click_types
        )
        summary.update(
            {
                "blocks_planned": self.cfg.blocks,
                "blocks_completed": sum(
                    1 for block in self._block_results if not block["aborted"]
                ),
                "trials_per_block": self.cfg.targets,
                "blocks": self._block_results,
                "subject": self.cfg.subject,
                "session_id": self.rec.session_id if self.rec else self.cfg.session_id,
                "data_dir": str(self.rec.dir) if self.rec else "",
                "software": {
                    "python": platform.python_version(),
                    "psychopy": psychopy.__version__,
                },
            }
        )
        if aborted:
            summary["aborted"] = True
        self._summary = summary
        self._done_at = now
        self.state = "done"
        self.reporter.session_end(now, summary, aborted=aborted)
        logger.info(
            "session {}: blocks={}/{} attempts={} hits={} misclicks={} bps={:.3f}",
            "aborted" if aborted else "finished",
            summary["blocks_completed"],
            self.cfg.blocks,
            summary["attempts"],
            summary["hits"],
            summary["misclicks"],
            summary["bps"],
        )
        if self.rec is not None:
            logger.success("saved {}", self.rec.dir)

    def _cleanup(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.input.close()
        self.reporter.close()
        try:
            self.win.setMouseVisible(True)
        except Exception:  # noqa: BLE001 - backend dependent
            logger.debug("could not restore the operating-system cursor")
        try:
            self.win.close()
        except Exception:  # noqa: BLE001  # pragma: no cover
            logger.exception("error closing the PsychoPy window")
        if self.rec is not None:
            self.rec.close()


def run_experiment(
    config: ExperimentConfig,
    recorder: Any,
    monitor: SessionMonitor | None = None,
) -> dict[str, Any]:
    """Run one session and return its summary."""
    config.validate()
    marker_sink = build_marker_sink(config)
    try:
        app = WebGridApp(
            config,
            recorder=recorder,
            marker_sink=marker_sink,
            monitor=monitor,
        )
    except BaseException:
        marker_sink.close()
        raise
    try:
        app.run()
    finally:
        app.close()
    return app.summary
