"""PsychoPy renderer and experiment loop for the web-grid paradigm."""

from __future__ import annotations

import platform
import random
import time
from pathlib import Path
from typing import Any

import psychopy
from loguru import logger
from psychopy import core, event, visual
from psychopy import logging as plog

from .config import ExperimentConfig
from .geometry import Cell, Layout
from .i18n import Strings
from .inputs import AutoPilot, UdpCursorSource
from .markers import (
    BLOCK_END,
    BLOCK_START,
    HIT,
    MISCLICK,
    SESSION_ABORT,
    SESSION_END,
    SESSION_START,
    TARGET_ONSET,
    TIMEOUT,
    MarkerSink,
    NullMarkerSink,
    build_marker_sink,
)
from .recorder import SessionRecorder
from .scoring import SessionStats, merge_stats
from .session import ClickEvent, FrameOutcome, Phase, SessionEngine, Target, TrialResult
from .station import NullView, SessionView

# Palette — close to Neuralink's Webgrid: white canvas, black lines, one
# saturated colour per click type.
BG = "#ffffff"
PANEL = "#f5f5f7"
PANEL_EDGE = "#d2d2d7"
GRID = "#111111"
TEXT = "#111111"
MUTED = "#6e6e73"
ACCENT = "#0a84ff"
ERROR = "#ff3b30"
HOVER = "#ededed"
CURSOR = "#111111"
CURSOR_EDGE = "#ffffff"
TARGET_COLORS = {1: "#0a84ff", 2: "#ff9500", 3: "#af52de"}


class WebGridApp:
    """Owns the window, stimuli, input devices and the session engine."""

    def __init__(
        self,
        config: ExperimentConfig,
        recorder: SessionRecorder | None = None,
        marker_sink: MarkerSink | None = None,
        dashboard: SessionView | NullView | None = None,
    ) -> None:
        self.cfg = config
        self.rec = recorder
        self.markers = marker_sink or NullMarkerSink()
        self.dash = dashboard or NullView()
        self._fps = 0.0
        self._next_publish = 0.0
        self.strings = Strings(config.language)

        window_size = (config.window_width, config.window_height)
        if config.fullscreen:
            try:
                import pyglet

                screens = pyglet.canvas.get_display().get_screens()
                screen = screens[min(max(config.screen, 0), len(screens) - 1)]
                window_size = (screen.width, screen.height)
            except Exception:  # noqa: BLE001 - backend fallback
                logger.debug("could not query the physical screen size")

        self.win = visual.Window(
            size=window_size,
            fullscr=config.fullscreen,
            screen=config.screen,
            units="pix",
            color=BG,
            allowGUI=False,
            winType="pyglet",
            checkTiming=False,
            title="BCI Web-Grid",
        )
        # PsychoPy buffers its own log entries; emit window-setup messages now
        # (routed to loguru by web_grid_paradigm.log) instead of at shutdown.
        plog.flush()
        logger.debug(
            "window opened: size={} fullscreen={}",
            tuple(int(v) for v in self.win.size),
            config.fullscreen,
        )
        width, height = (int(v) for v in self.win.size)
        try:
            self.layout = Layout.create(width, height, config.rows, config.cols)
        except BaseException:
            self.win.close()
            raise
        self.ui = max(0.65, min(2.2, min(width / 1280, height / 800)))

        self.mouse = event.Mouse(win=self.win, visible=not config.hide_cursor)
        self._prev_mouse = [False, False, False]
        self._auto = AutoPilot(config.demo_speed) if config.input == "demo" else None
        self._udp = (
            UdpCursorSource(config.udp_host, config.udp_port, config.smoothing)
            if config.input == "udp"
            else None
        )

        # One engine per block; the shared RNG keeps blocks reproducible but
        # gives each block a different target sequence.
        self._rng = random.Random(config.seed)
        self.block = 1
        self.engine = SessionEngine(config, self.layout, self._rng)
        self._block_results: list[dict[str, Any]] = []
        self._block_stats: list[tuple[SessionStats, float]] = []
        self._block_closed = False
        self._rest_until = 0.0
        if self.rec is not None:
            self.rec.block = self.block
        self.state = "intro"  # wait | intro | countdown | run | rest | done
        self._cursor_px: tuple[float, float] = (0.0, 0.0)
        self._last_frame = core.getTime()
        self._done_at = 0.0
        self._exit = False
        self._closed = False
        self._finalized = False
        self._summary: dict[str, Any] = {}

        self._pending_target_onset = False
        self._pending_feedback_start = False
        self._cursor_flash_until = 0.0
        self._miss_cell: Cell | None = None
        self._miss_until = 0.0
        self.countdown_start = 0.0

        self._build_stimuli()
        self._configure_intro_texts()
        self._dashboard_static()
        if self.rec is not None:
            self.rec.event(
                "session_open",
                self._last_frame,
                detail={
                    "psychopy": psychopy.__version__,
                    "python": platform.python_version(),
                },
            )
        if config.skip_instructions:
            self._begin_countdown(core.getTime())

    # ------------------------------------------------------------------
    # construction helpers
    # ------------------------------------------------------------------
    def _build_stimuli(self) -> None:
        layout = self.layout
        w, h = layout.window_w, layout.window_h
        ui = self.ui

        # Static white board with thin black grid lines, captured once.
        board = visual.Rect(
            self.win,
            width=layout.board_w,
            height=layout.board_h,
            pos=layout.board_centre,
            fillColor="#ffffff",
            lineColor=None,
            units="pix",
        )
        lines = [board]
        board_cx, board_cy = layout.board_centre
        for col in range(layout.cols + 1):
            x = layout.left + col * layout.pitch + layout.line / 2
            lines.append(
                visual.Rect(
                    self.win,
                    width=layout.line,
                    height=layout.board_h,
                    pos=(x, board_cy),
                    fillColor=GRID,
                    lineColor=None,
                    units="pix",
                )
            )
        for row in range(layout.rows + 1):
            y = layout.top - row * layout.pitch - layout.line / 2
            lines.append(
                visual.Rect(
                    self.win,
                    width=layout.board_w,
                    height=layout.line,
                    pos=(board_cx, y),
                    fillColor=GRID,
                    lineColor=None,
                    units="pix",
                )
            )
        self.grid_bg = visual.BufferImageStim(self.win, stim=lines)
        del lines

        self.hover_stim = visual.Rect(
            self.win,
            width=layout.cell,
            height=layout.cell,
            fillColor=HOVER,
            lineColor=None,
            units="pix",
        )
        self.target_stim = visual.Rect(
            self.win,
            width=layout.cell,
            height=layout.cell,
            fillColor=TARGET_COLORS[1],
            lineColor=None,
            units="pix",
        )
        self.target_hover = visual.Rect(
            self.win,
            width=layout.cell,
            height=layout.cell,
            fillColor="#000000",
            opacity=0.18,
            lineColor=None,
            units="pix",
        )
        self.miss_stim = visual.Rect(
            self.win,
            width=layout.cell,
            height=layout.cell,
            fillColor=ERROR,
            lineColor=None,
            units="pix",
        )
        radius = max(5.0, min(12.0, layout.cell * 0.16))
        self.cursor_stim = visual.Circle(
            self.win,
            radius=radius,
            fillColor=CURSOR,
            lineColor=CURSOR_EDGE,
            lineWidth=2,
            units="pix",
        )
        self.dwell_bar = visual.Rect(
            self.win,
            width=2,
            height=max(3.0, layout.cell * 0.05),
            fillColor="#ffffff",
            lineColor=GRID,
            lineWidth=1,
            units="pix",
        )

        # Animal-facing task screen has no text.  The only chrome is a
        # fixation cross during the countdown.
        fix = 18 * ui
        self.fixation_bg = visual.Circle(
            self.win,
            radius=26 * ui,
            fillColor="#ffffff",
            lineColor=None,
            units="pix",
        )
        self.fixation_h = visual.Line(
            self.win,
            start=(-fix, 0),
            end=(fix, 0),
            lineColor=TEXT,
            lineWidth=2,
            units="pix",
        )
        self.fixation_v = visual.Line(
            self.win,
            start=(0, -fix),
            end=(0, fix),
            lineColor=TEXT,
            lineWidth=2,
            units="pix",
        )

        # Optional human instruction screen; skipped by default.
        panel_w = min(w * 0.72, 900 * ui)
        panel_h = h * 0.56
        self.panel = visual.Rect(
            self.win,
            width=panel_w,
            height=panel_h,
            pos=(0, 0),
            fillColor=PANEL,
            lineColor=PANEL_EDGE,
            lineWidth=2,
            units="pix",
        )
        self.intro_title = self._text(
            self.strings["title"], 46 * ui, TEXT, (0, h * 0.20), bold=True
        )
        self.intro_subtitle = self._text(
            self.strings["subtitle"], 20 * ui, MUTED, (0, h * 0.145)
        )
        self.intro_body = self._text(
            "", 21 * ui, TEXT, (0, h * 0.02), wrap=panel_w * 0.84
        )
        self.intro_mode = self._text("", 17 * ui, ACCENT, (0, -h * 0.08))
        self.intro_start = self._text(
            self.strings["start_hint"], 19 * ui, TEXT, (0, -h * 0.17)
        )

    def _text(
        self,
        text: str,
        height: float,
        color: str = TEXT,
        pos: tuple[float, float] = (0, 0),
        anchor: str = "center",
        wrap: float | None = None,
        bold: bool = False,
        align: str = "center",
    ) -> visual.TextStim:
        return visual.TextStim(
            self.win,
            text=text,
            font=self.cfg.font,
            height=height,
            color=color,
            pos=pos,
            units="pix",
            anchorHoriz=anchor,
            anchorVert="center",
            alignText=align,
            wrapWidth=wrap,
            bold=bold,
        )

    def _configure_intro_texts(self) -> None:
        if self.cfg.selection == "dwell":
            body_key = "instr_dwell"
        elif self.cfg.click_types > 1:
            body_key = "instr_click_multi"
        else:
            body_key = "instr_click"
        self.intro_body.text = self.strings[body_key]
        self.intro_mode.text = {
            "mouse": self.strings["mode_mouse"],
            "keyboard": self.strings["mode_keyboard"],
            "udp": self.strings.format("mode_udp", port=self.cfg.udp_port),
            "demo": self.strings["mode_demo"],
        }[self.cfg.input]

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
        centre = self.layout.centre_px(cell)
        self.engine.target = Target(
            index=15,
            cell=cell,
            required_button=min(self.cfg.click_types, 3),
            onset=now - 1.3,
            start_px=(0.0, 0.0),
            centre_px=centre,
        )
        self.engine.phase = Phase.RUNNING
        self._cursor_px = (
            centre[0] - self.layout.cell * 0.45,
            centre[1] - self.layout.cell * 0.1,
        )
        self._draw_run(now)
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

            if "escape" in keys or self.dash.stop_requested:
                if self.dash.stop_requested:
                    logger.warning("stop requested from the web panel; ending session")
                else:
                    logger.warning("escape pressed during '{}'; ending session", self.state)
                if self.state in ("run", "countdown", "intro", "rest"):
                    self._finalize(now, aborted=True)
                self._exit = True
                break

            if self.state == "intro":
                if self._start_requested(now, keys):
                    self._begin_countdown(now)
                else:
                    self._draw_intro()
                    self.win.flip()
                    continue

            if self.state == "countdown":
                if now - self.countdown_start >= self.cfg.countdown_seconds:
                    self._begin_run(now)
                else:
                    self._poll_cursor_only(now)
                    self._draw_countdown(now)
                    self.win.flip()
                    continue

            if self.state == "rest":
                if now >= self._rest_until:
                    self._next_block(now)
                else:
                    # Blank inter-block rest.
                    self._poll_cursor_only(now)
                    self.win.flip()
                    continue

            if self.state == "run":
                self._run_frame(now, dt, keys)
            elif self.state == "done":
                self._draw_done()
                self.win.flip()
                if (
                    (self.cfg.auto_exit and now - self._done_at >= 2.5)
                    or "space" in keys
                    or "return" in keys
                    or any(self.mouse.getPressed())
                ):
                    self._exit = True

    def _start_requested(self, now: float, keys: list[str]) -> bool:
        if "space" in keys or "return" in keys:
            return True
        pressed = [bool(v) for v in self.mouse.getPressed()]
        self._prev_mouse = pressed
        if any(pressed):
            return True
        if self.cfg.input == "udp" and self._udp is not None:
            state = self._udp.poll(now)
            if state is not None:
                self._cursor_px = self.layout.norm_to_px(state.x, state.y)
                return bool(state.clicks)
        return False

    def _begin_countdown(self, now: float) -> None:
        self.state = "countdown"
        self.countdown_start = now
        logger.info(
            "block {}/{}: countdown started ({} s)",
            self.block,
            self.cfg.blocks,
            self.cfg.countdown_seconds,
        )
        if self.rec is not None:
            if self.block == 1:
                self.rec.event(
                    "instructions_end",
                    now,
                    detail={"skipped": self.cfg.skip_instructions},
                )
            self.rec.event("countdown_start", now)
        if self.cfg.countdown_seconds <= 0:
            self._begin_run(now)

    def _begin_run(self, now: float) -> None:
        self.state = "run"
        self._pending_target_onset = True
        self._pending_feedback_start = False
        self._miss_cell = None
        self._miss_until = 0.0
        self._prev_mouse = [bool(v) for v in self.mouse.getPressed()]
        self.engine.begin(now, *self._cursor_px)
        self._block_closed = False
        logger.info(
            "block {}/{} started: {} trials on a {}x{} grid",
            self.block,
            self.cfg.blocks,
            self.cfg.targets,
            self.cfg.rows,
            self.cfg.cols,
        )
        if self.block == 1:
            self.markers.send(
                SESSION_START, t=now, detail={"subject": self.cfg.subject}
            )
        self.markers.send(BLOCK_START, t=now, detail={"block": self.block})
        if self.rec is not None:
            if self.block == 1:
                self.rec.event(
                    "run_start",
                    now,
                    detail={
                        "rows": self.cfg.rows,
                        "cols": self.cfg.cols,
                        "blocks": self.cfg.blocks,
                        "trials_per_block": self.cfg.targets,
                        "click_types": self.cfg.click_types,
                        "selection": self.cfg.selection,
                    },
                )
            self.rec.event(
                "block_start",
                now,
                detail={"block": self.block, "trials": self.cfg.targets},
            )

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
        self.dash.set_blocks(self._block_results)
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
        self.markers.send(
            BLOCK_END,
            t=now,
            detail={"block": self.block, "hits": result["hits"]},
        )
        if self.rec is not None:
            self.rec.event(
                "block_end",
                now,
                detail={
                    "block": self.block,
                    "aborted": aborted,
                    "attempts": result["attempts"],
                    "hits": result["hits"],
                    "misclicks": result["misclicks"],
                    "bps": round(result["bps"], 4),
                },
            )

    def _end_block(self, now: float) -> None:
        self._close_block(now, aborted=False)
        if self.block >= self.cfg.blocks:
            self._finalize(now, aborted=False)
            return
        self.state = "rest"
        self._rest_until = now + self.cfg.block_rest
        logger.info("rest {} s before block {}", self.cfg.block_rest, self.block + 1)
        if self.rec is not None:
            self.rec.event(
                "rest_start", now, detail={"seconds": self.cfg.block_rest}
            )

    def _next_block(self, now: float) -> None:
        self.block += 1
        previous = self.engine.target.cell if self.engine.target else None
        self.engine = SessionEngine(
            self.cfg, self.layout, self._rng, avoid_first=previous
        )
        if self._auto is not None:
            # Fresh autopilot state so a repeated target is still clicked.
            self._auto = AutoPilot(self.cfg.demo_speed, self._auto_position())
        if self.rec is not None:
            self.rec.block = self.block
        self._begin_countdown(now)

    # ------------------------------------------------------------------
    # live dashboard
    # ------------------------------------------------------------------
    PUBLISH_INTERVAL = 1 / 30  # cursor/state updates sent at most 30 Hz

    def _publish(self, now: float, dt: float) -> None:
        """Push the current state to the dashboard (cheap; rate limited)."""
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
        block_elapsed = engine.elapsed(now) if engine.session_start is not None else None
        self.dash.update(
            phase=phase,
            block=self.block,
            trials_done=engine.stats.attempts,
            target=target_info,
            dwell_progress=round(engine.dwell_progress, 3),
            block_elapsed=round(block_elapsed, 2) if block_elapsed is not None else None,
            block_bps=(
                round(engine.summary(now)["bps"], 3)
                if engine.stats.attempts
                else None
            ),
            flash_until=(
                time.time() + (self._cursor_flash_until - now)
                if self._cursor_flash_until > now
                else None
            ),
            aborted=engine.aborted and self.state == "done",
        )
        self.dash.cursor(*self._cursor_px, fps=self._fps)

    def _dashboard_static(self) -> None:
        """One-off session info for the dashboard."""
        layout = self.layout
        self.dash.update(
            subject=self.cfg.subject,
            session_id=self.rec.session_id if self.rec else self.cfg.session_id,
            data_dir=str(self.rec.dir) if self.rec else "",
            config=self.cfg.to_dict(),
            grid={
                "rows": layout.rows,
                "cols": layout.cols,
                "left": layout.left,
                "top": layout.top,
                "pitch": layout.pitch,
                "line": layout.line,
            },
        )

    def _auto_position(self) -> tuple[float, float]:
        return self.layout.px_to_norm(*self._cursor_px)

    def _run_frame(self, now: float, dt: float, keys: list[str]) -> None:
        if self.engine.phase is Phase.DONE:
            self._end_block(now)
            self.win.flip()
            return

        if (
            self.engine.phase is Phase.FEEDBACK
            and not self._pending_feedback_start
            and now >= self.engine.feedback_until
        ) or (self.engine.phase is Phase.ITI and now >= self.engine.iti_until):
            target = self.engine.advance(now, *self._cursor_px)
            if self.engine.phase is Phase.DONE:
                self._end_block(now)
                self.win.flip()
                return
            if self.engine.phase is Phase.ITI:
                self._log_iti_start(now)
            if target is not None:
                self._pending_target_onset = True

        if self.engine.phase is Phase.RUNNING and not self._pending_target_onset:
            x, y, clicks = self._read_input(now, dt, keys)
            outcome = self.engine.update(now, x, y, clicks)
            self._handle_outcome(outcome)
        elif self.engine.phase in (Phase.FEEDBACK, Phase.ITI):
            # Keep the devices fresh during feedback/ITI (especially the mouse
            # button edges) but discard any click.
            self._read_input(now, dt, keys)

        self._draw_run(now)
        flip_time = self.win.flip()

        if self._pending_target_onset:
            self._mark_target_onset(flip_time)
            self._pending_target_onset = False
        if self._pending_feedback_start:
            self.engine.feedback_until = flip_time + self.cfg.feedback
            self._pending_feedback_start = False

    def _log_iti_start(self, now: float) -> None:
        logger.debug(
            "block {} ITI {} s after trial {}",
            self.block,
            self.cfg.iti,
            self.engine.stats.attempts,
        )
        if self.rec is not None:
            self.rec.event(
                "iti_start",
                now,
                target_index=self.engine.stats.attempts,
                detail={"seconds": self.cfg.iti},
            )

    def _handle_outcome(self, outcome: FrameOutcome) -> None:
        for click in outcome.clicks:
            self._log_click(click)
        if outcome.trial is not None:
            self._log_trial(outcome.trial)

    def _log_click(self, click: ClickEvent) -> None:
        target = self.engine.target
        x_norm, y_norm = self.layout.px_to_norm(click.x_px, click.y_px)
        if self.cfg.selection == "dwell" and click.correct and click.button is None:
            name = "dwell_select"
        else:
            name = "click"
        if self.rec is not None:
            self.rec.event(
                name,
                click.time,
                x=x_norm,
                y=y_norm,
                button=click.button,
                cell=click.cell,
                target_index=target.index if target else None,
                detail={
                    "correct": click.correct,
                    "selection": self.cfg.selection,
                    "required_button": target.required_button if target else None,
                },
            )
        logger.debug(
            "{} button={} cell={} correct={}",
            name,
            click.button,
            click.cell.label if click.cell else None,
            click.correct,
        )
        if self.cfg.selection == "dwell":
            # Clicks are only recorded during dwell mode; they do not select.
            return
        if not click.correct:
            self.markers.send(
                MISCLICK,
                t=click.time,
                detail={
                    "button": click.button,
                    "required_button": target.required_button if target else None,
                },
            )
            self._cursor_flash_until = click.time + 0.25
            if click.cell is not None:
                self._miss_cell = click.cell
                self._miss_until = click.time + 0.2

    def _log_trial(self, trial: TrialResult) -> None:
        self.dash.add_trial(
            {
                "block": self.block,
                "trial": trial.index,
                "cell": trial.cell.label,
                "outcome": trial.outcome,
                "reason": trial.reason,
                "rt": round(trial.rt, 4),
                "misclicks": trial.misclicks,
                "path_efficiency": (
                    round(trial.path_efficiency, 4)
                    if trial.path_efficiency is not None
                    else None
                ),
            }
        )
        logger.info(
            "block {} trial {}/{} {} cell={} rt={:.3f}s misclicks={}",
            self.block,
            trial.index,
            self.cfg.targets,
            trial.outcome,
            trial.cell.label,
            trial.rt,
            trial.misclicks,
        )
        if self.rec is not None:
            self.rec.trial(trial)
            self.rec.event(
                "hit" if trial.correct else "timeout",
                trial.offset,
                cell=trial.cell,
                target_index=trial.index,
                detail={
                    "rt": round(trial.rt, 4),
                    "misclicks": trial.misclicks,
                    "reason": trial.reason,
                    "required_button": trial.required_button,
                    "path_efficiency": (
                        round(trial.path_efficiency, 4)
                        if trial.path_efficiency is not None
                        else None
                    ),
                },
            )
        self.markers.send(
            HIT if trial.correct else TIMEOUT,
            t=trial.offset,
            detail={
                "block": self.block,
                "target_index": trial.index,
                "row": trial.cell.row + 1,
                "col": trial.cell.col + 1,
                "required_button": trial.required_button,
                "rt": round(trial.rt, 4),
            },
        )
        self._pending_feedback_start = True

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
        if self.rec is not None:
            x_norm, y_norm = self.layout.px_to_norm(*self._cursor_px)
            self.rec.event(
                "target_onset",
                flip_time,
                x=x_norm,
                y=y_norm,
                cell=target.cell,
                target_index=target.index,
                detail={
                    "onset": flip_time,
                    "selection": self.cfg.selection,
                    "required_button": target.required_button,
                },
            )
        self.markers.send(
            TARGET_ONSET,
            t=flip_time,
            detail={
                "block": self.block,
                "target_index": target.index,
                "row": target.cell.row + 1,
                "col": target.cell.col + 1,
                "required_button": target.required_button,
            },
        )

    # ------------------------------------------------------------------
    # input
    # ------------------------------------------------------------------
    def _read_input(
        self, now: float, dt: float, keys: list[str]
    ) -> tuple[float, float, list[int]]:
        clicks: list[int] = []
        x, y = self._cursor_px
        width, height = self.layout.window_w, self.layout.window_h

        if self.cfg.input == "mouse":
            try:
                x, y = self.mouse.getPos()
            except Exception:  # noqa: BLE001 - backend focus edge case
                logger.debug("mouse position unavailable; keeping the last position")
                x, y = self._cursor_px
            pressed = [bool(v) for v in self.mouse.getPressed()]
            # PsychoPy order is left, middle, right; expose left=1, right=2, middle=3.
            for index, button in ((0, 1), (2, 2), (1, 3)):
                if (
                    button <= self.cfg.click_types
                    and pressed[index]
                    and not self._prev_mouse[index]
                ):
                    clicks.append(button)
            self._prev_mouse = pressed
        elif self.cfg.input == "keyboard":
            step_x = self.cfg.keyboard_step * width / 2
            step_y = self.cfg.keyboard_step * height / 2
            if "left" in keys:
                x -= step_x
            if "right" in keys:
                x += step_x
            if "up" in keys:
                y += step_y
            if "down" in keys:
                y -= step_y
            if "space" in keys or "return" in keys:
                clicks.append(1)
            for key, button in (("1", 1), ("2", 2), ("3", 3)):
                if key in keys:
                    clicks.append(button)
        elif self.cfg.input == "udp" and self._udp is not None:
            state = self._udp.poll(now)
            if state is not None:
                self._cursor_px = self.layout.norm_to_px(state.x, state.y)
                clicks.extend(state.clicks)
            x, y = self._cursor_px
        elif self.cfg.input == "demo" and self._auto is not None:
            target = self.engine.target
            if target is not None:
                nx, ny = self.layout.px_to_norm(*target.centre_px)
                state = self._auto.poll(dt, (nx, ny))
                self._cursor_px = self.layout.norm_to_px(state.x, state.y)
                if state.clicks:
                    clicks.append(target.required_button)
            x, y = self._cursor_px

        x = min(width / 2, max(-width / 2, float(x)))
        y = min(height / 2, max(-height / 2, float(y)))
        self._cursor_px = (x, y)
        return (
            x,
            y,
            [button for button in clicks if 1 <= button <= self.cfg.click_types],
        )

    def _poll_cursor_only(self, now: float) -> None:
        if self.cfg.input == "mouse":
            try:
                self._cursor_px = self.mouse.getPos()
            except Exception:  # noqa: BLE001 - backend focus edge case
                logger.debug("mouse position unavailable; keeping the last position")
            self._prev_mouse = [bool(v) for v in self.mouse.getPressed()]
        elif self.cfg.input == "udp" and self._udp is not None:
            state = self._udp.poll(now)
            if state is not None:
                self._cursor_px = self.layout.norm_to_px(state.x, state.y)

    # ------------------------------------------------------------------
    # drawing
    # ------------------------------------------------------------------
    def _draw_intro(self) -> None:
        self.panel.draw()
        self.intro_title.draw()
        self.intro_subtitle.draw()
        self.intro_body.draw()
        self.intro_mode.draw()
        self.intro_start.draw()

    def _draw_countdown(self, now: float) -> None:
        # No numbers or words: only a fixation cross before the task starts.
        self.grid_bg.draw()
        self.fixation_bg.draw()
        self.fixation_h.draw()
        self.fixation_v.draw()

    def _draw_run(self, now: float) -> None:
        self.grid_bg.draw()
        # During the inter-trial interval only the empty grid and cursor show.
        target = self.engine.target if self.engine.phase is not Phase.ITI else None
        cursor_cell = self.layout.cell_at_px(*self._cursor_px)

        if target is not None:
            target_x, target_y = target.centre_px
            if cursor_cell is not None and cursor_cell != target.cell:
                hover_x, hover_y = self.layout.centre_px(cursor_cell)
                self.hover_stim.pos = (hover_x, hover_y)
                self.hover_stim.draw()

            colour = TARGET_COLORS.get(target.required_button, ACCENT)
            self.target_stim.pos = (target_x, target_y)
            self.target_stim.fillColor = colour
            self.target_stim.draw()

            if cursor_cell == target.cell and self.engine.phase is Phase.RUNNING:
                self.target_hover.pos = (target_x, target_y)
                self.target_hover.draw()

            if self._miss_cell is not None and now < self._miss_until:
                miss_x, miss_y = self.layout.centre_px(self._miss_cell)
                self.miss_stim.pos = (miss_x, miss_y)
                self.miss_stim.draw()

            progress = self.engine.dwell_progress
            if progress > 0.01:
                inner = self.layout.cell * 0.72
                bar_h = max(3.0, self.layout.cell * 0.05)
                bar_w = max(1.0, inner * progress)
                self.dwell_bar.width = bar_w
                self.dwell_bar.pos = (
                    target_x - inner / 2 + bar_w / 2,
                    target_y - self.layout.cell / 2 + bar_h + 2,
                )
                self.dwell_bar.draw()

        self.cursor_stim.pos = self._cursor_px
        self.cursor_stim.fillColor = ERROR if now < self._cursor_flash_until else CURSOR
        self.cursor_stim.draw()

    def _draw_done(self) -> None:
        # Blank end screen: the animal sees no text; the saved path is printed
        # to the experimenter console.
        return None

    # ------------------------------------------------------------------
    # finalisation
    # ------------------------------------------------------------------
    def _finalize(self, now: float, aborted: bool) -> None:
        if self._finalized:
            return
        self._finalized = True
        # An abort mid-block records the partial block; aborting during the
        # wait/countdown before a block starts records nothing for it.
        self._close_block(now, aborted=aborted)
        summary = merge_stats(
            self._block_stats, self.cfg.n_cells, self.cfg.click_types
        )
        summary.update(
            {
                "blocks_planned": self.cfg.blocks,
                "blocks_completed": sum(
                    1 for b in self._block_results if not b["aborted"]
                ),
                "trials_per_block": self.cfg.targets,
                "blocks": self._block_results,
            }
        )
        summary.update(
            {
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
        if self.rec is not None:
            self.rec.write_summary(summary)
            self.rec.event(
                "abort" if aborted else "run_end",
                now,
                detail={
                    "attempts": summary["attempts"],
                    "hits": summary["hits"],
                    "misclicks": summary["misclicks"],
                    "bps": round(summary["bps"], 4),
                },
            )
        self.markers.send(
            SESSION_ABORT if aborted else SESSION_END,
            t=now,
            detail={"attempts": summary["attempts"], "hits": summary["hits"]},
        )
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
        self.dash.update(
            phase="done",
            aborted=bool(aborted),
            target=None,
            session_summary={
                k: summary[k]
                for k in ("attempts", "hits", "misclicks", "timeouts", "bps", "duration_s")
            },
        )

    def _cleanup(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._udp is not None:
            self._udp.close()
        try:
            self.markers.close()
        except Exception:  # noqa: BLE001 - logged via logger.exception
            logger.exception("error closing event markers")
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
    recorder: SessionRecorder,
    dashboard: SessionView | NullView | None = None,
) -> dict[str, Any]:
    """Run one session and return its summary."""
    config.validate()
    marker_sink = build_marker_sink(config)
    try:
        app = WebGridApp(
            config,
            recorder=recorder,
            marker_sink=marker_sink,
            dashboard=dashboard,
        )
    except BaseException:
        marker_sink.close()
        raise
    try:
        app.run()
    finally:
        app.close()
    return app.summary
