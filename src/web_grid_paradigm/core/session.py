"""Trial state machine for the web-grid task (no PsychoPy dependency).

The runner owns rendering and input; this module owns the experimental logic:
which cell is the target, when it appeared, how long the cursor dwelt on it,
whether a click was correct, and when the session ends.  Keeping this pure
makes the paradigm easy to unit-test and to replay from recorded data.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum

from .config import ExperimentConfig
from .geometry import Cell, Layout, TargetBag
from .scoring import SessionStats


class Phase(str, Enum):
    READY = "ready"
    RUNNING = "running"
    FEEDBACK = "feedback"
    ITI = "iti"  # inter-trial interval: no target on screen
    DONE = "done"


@dataclass(slots=True)
class Target:
    index: int  # 1-based attempt number
    cell: Cell
    required_button: int  # 1=left, 2=right, 3=middle
    onset: float
    start_px: tuple[float, float]
    centre_px: tuple[float, float]


@dataclass(slots=True)
class ClickEvent:
    time: float
    x_px: float
    y_px: float
    button: int | None
    correct: bool
    cell: Cell | None


@dataclass(slots=True)
class TrialResult:
    index: int
    cell: Cell
    required_button: int
    onset: float
    offset: float
    outcome: str  # "hit" | "timeout"
    reason: str
    correct: bool
    rt: float
    misclicks: int
    button: int | None
    path_px: float
    straight_px: float
    path_efficiency: float | None
    dwell: bool


@dataclass(slots=True)
class FrameOutcome:
    clicks: list[ClickEvent] = field(default_factory=list)
    trial: TrialResult | None = None


class SessionEngine:
    """Drives one block of target-selection trials."""

    def __init__(
        self,
        config: ExperimentConfig,
        layout: Layout,
        rng: random.Random | None = None,
        *,
        avoid_first: Cell | None = None,
    ) -> None:
        self.config = config
        self.layout = layout
        self.stats = SessionStats()
        self.phase = Phase.READY
        self.target: Target | None = None
        self.session_start: float | None = None
        self.session_end: float | None = None
        self.feedback_until = 0.0
        self.iti_until = 0.0
        self.aborted = False

        self._rng = rng or random.Random()
        self._bag = TargetBag(config.rows, config.cols, self._rng)
        self._prev_px: tuple[float, float] | None = None
        self._current_px: tuple[float, float] = (0.0, 0.0)
        self._path_px = 0.0
        self._dwell_s = 0.0
        self._trial_misclicks = 0
        self._last_update: float | None = None
        # A new block must not open on the cell the previous block ended on.
        self._last_cell: Cell | None = avoid_first

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def begin(self, now: float, x_px: float = 0.0, y_px: float = 0.0) -> Target:
        if self.phase is not Phase.READY:
            raise RuntimeError("session already started")
        self.session_start = now
        self.phase = Phase.RUNNING
        return self._start_target(now, x_px, y_px)

    def retime_onset(self, now: float) -> None:
        """Set the target onset to the flip that actually displayed it.

        The runner starts the next trial just before drawing the frame; once
        the frame is on screen it calls this method so reaction times and the
        marker timestamp refer to photon onset rather than to draw setup.
        """
        if self.target is not None and self.phase is Phase.RUNNING:
            self.target.onset = now
            self._last_update = now

    def _start_target(self, now: float, x_px: float, y_px: float) -> Target:
        cell = self._bag.next(avoid=self._last_cell)
        self._last_cell = cell
        centre = self.layout.centre_px(cell)
        # Dwell mode has no button channel; a single blue target is enough.
        required_button = (
            1
            if self.config.selection == "dwell"
            else self._rng.randint(1, self.config.click_types)
        )
        self.target = Target(
            index=self.stats.attempts + 1,
            cell=cell,
            required_button=required_button,
            onset=now,
            start_px=(x_px, y_px),
            centre_px=centre,
        )
        self._prev_px = (x_px, y_px)
        self._current_px = (x_px, y_px)
        self._path_px = 0.0
        self._dwell_s = 0.0
        self._trial_misclicks = 0
        self._last_update = now
        self.phase = Phase.RUNNING
        return self.target

    # ------------------------------------------------------------------
    # per-frame update
    # ------------------------------------------------------------------
    def update(
        self,
        now: float,
        x_px: float,
        y_px: float,
        clicks: list[int] | tuple[int, ...] = (),
    ) -> FrameOutcome:
        outcome = FrameOutcome()
        if self.phase is not Phase.RUNNING or self.target is None:
            return outcome

        x_px = _clamp(x_px, -self.layout.window_w / 2, self.layout.window_w / 2)
        y_px = _clamp(y_px, -self.layout.window_h / 2, self.layout.window_h / 2)
        dt = 0.0 if self._last_update is None else now - self._last_update
        dt = _clamp(dt, 0.0, 0.25)
        if self._prev_px is not None:
            step = math.dist((x_px, y_px), self._prev_px)
            # Ignore implausible teleports (for example a device reset).
            if step <= 0.5 * math.hypot(self.layout.window_w, self.layout.window_h):
                self._path_px += step
        self._prev_px = (x_px, y_px)
        self._current_px = (x_px, y_px)
        self._last_update = now

        cell = self.layout.cell_at_px(x_px, y_px)
        on_target = cell == self.target.cell
        valid_buttons = [b for b in clicks if 1 <= int(b) <= self.config.click_types]

        # Dwell selection is evaluated before clicks: in dwell mode clicks are
        # not a selection channel, but they are still recorded for QC.
        if self.config.selection == "dwell":
            for button in valid_buttons:
                outcome.clicks.append(
                    ClickEvent(now, x_px, y_px, int(button), False, cell)
                )
            self._dwell_s = self._dwell_s + dt if on_target else 0.0
            if self._dwell_s >= self.config.dwell_time:
                trial = self._finish(now, "hit", "dwell", button=None, dwell=True)
                outcome.trial = trial
                outcome.clicks.append(ClickEvent(now, x_px, y_px, None, True, cell))
                return outcome
        else:
            for button in valid_buttons:
                button = int(button)
                correct = on_target and button == self.target.required_button
                outcome.clicks.append(
                    ClickEvent(now, x_px, y_px, button, correct, cell)
                )
                if correct:
                    outcome.trial = self._finish(
                        now, "hit", "click", button=button, dwell=False
                    )
                    return outcome
                self.stats.add_misclick()
                self._trial_misclicks += 1

        if (
            self.config.trial_timeout > 0
            and now - self.target.onset >= self.config.trial_timeout
        ):
            outcome.trial = self._finish(
                now, "timeout", "trial_timeout", button=None, dwell=False
            )
            return outcome

        if (
            self.config.max_seconds > 0
            and self.session_start is not None
            and now - self.session_start >= self.config.max_seconds
        ):
            outcome.trial = self._finish(
                now, "timeout", "session_limit", button=None, dwell=False
            )
        return outcome

    def _finish(
        self, now: float, outcome: str, reason: str, *, button: int | None, dwell: bool
    ) -> TrialResult:
        assert self.target is not None
        target = self.target
        rt = max(0.0, now - target.onset)
        straight = math.dist(target.centre_px, target.start_px)
        efficiency = None
        if straight > 1.0 and self._path_px > 1.0:
            efficiency = min(1.0, straight / self._path_px)
        trial = TrialResult(
            index=target.index,
            cell=target.cell,
            required_button=target.required_button,
            onset=target.onset,
            offset=now,
            outcome=outcome,
            reason=reason,
            correct=outcome == "hit",
            rt=rt,
            misclicks=self._trial_misclicks,
            button=button,
            path_px=self._path_px,
            straight_px=straight,
            path_efficiency=efficiency,
            dwell=dwell,
        )
        self.stats.add_trial(hit=trial.correct, rt=rt, efficiency=efficiency)
        self.phase = Phase.FEEDBACK
        self.feedback_until = now + self.config.feedback
        return trial

    # ------------------------------------------------------------------
    # between trials
    # ------------------------------------------------------------------
    def advance(
        self,
        now: float,
        x_px: float | None = None,
        y_px: float | None = None,
    ) -> Target | None:
        """Move on after feedback: into the ITI, then to the next trial.

        Sequence between two trials: FEEDBACK -> ITI (``config.iti`` s, skipped
        when 0) -> next target.  No ITI follows the last trial of a block.
        Returns the new target, or ``None`` while still waiting / when done.
        """
        if self.target is None:
            return None
        if self.phase is Phase.FEEDBACK:
            if now < self.feedback_until:
                return None
            if self._block_over(now):
                self._end(now)
                return None
            if self.config.iti > 0:
                self.phase = Phase.ITI
                self.iti_until = now + self.config.iti
                return None
        elif self.phase is Phase.ITI:
            if now < self.iti_until:
                return None
            if self._block_over(now):
                self._end(now)
                return None
        else:
            return None
        if x_px is not None and y_px is not None:
            self._current_px = (float(x_px), float(y_px))
        return self._start_target(now, *self._current_px)

    def _block_over(self, now: float) -> bool:
        if (
            self.config.max_seconds > 0
            and self.session_start is not None
            and now - self.session_start >= self.config.max_seconds
        ):
            return True
        return self.stats.attempts >= self.config.targets

    def _end(self, now: float) -> None:
        self.phase = Phase.DONE
        self.session_end = now

    def abort(self, now: float) -> None:
        self.aborted = True
        self.stats.aborted = True
        self.session_end = now
        self.phase = Phase.DONE

    # ------------------------------------------------------------------
    # read-only helpers for the renderer
    # ------------------------------------------------------------------
    @property
    def dwell_progress(self) -> float:
        if (
            self.phase is not Phase.RUNNING
            or self.config.selection != "dwell"
            or self.config.dwell_time <= 0
        ):
            return 0.0
        return min(1.0, self._dwell_s / self.config.dwell_time)

    def elapsed(self, now: float) -> float:
        if self.session_start is None:
            return 0.0
        end = self.session_end if self.session_end is not None else now
        return max(0.0, end - self.session_start)

    def summary(self, now: float) -> dict:
        data = self.stats.summary(
            self.elapsed(now), self.config.n_cells, self.config.click_types
        )
        data["session_start"] = self.session_start
        data["session_end"] = self.session_end if self.session_end is not None else now
        return data


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))
