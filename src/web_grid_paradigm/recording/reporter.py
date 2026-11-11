"""All session output in one place: data files, event markers, live monitor.

The runner decides *what* happens; :class:`Reporter` decides what to write
where.  Keeping this at one boundary means the CSV columns, the LSL marker
codes and the web panel payload can never drift apart.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from ..core.config import ExperimentConfig
from ..core.geometry import Layout
from ..core.monitor import NullMonitor, SessionMonitor
from ..core.session import ClickEvent, Target, TrialResult
from ..reward.sink import RewardSink, build_reward_sink
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
)
from .recorder import SessionRecorder


class Reporter:
    """Writes one session's events to every configured output."""

    def __init__(
        self,
        config: ExperimentConfig,
        layout: Layout,
        recorder: SessionRecorder | None = None,
        marker_sink: MarkerSink | None = None,
        monitor: SessionMonitor | None = None,
        reward_sink: RewardSink | None = None,
        own_reward_sink: bool = True,
    ) -> None:
        self.cfg = config
        self.layout = layout
        self.rec = recorder
        self.markers = marker_sink or NullMarkerSink()
        self.monitor = monitor or NullMonitor()
        self._owns_reward_sink = reward_sink is None or own_reward_sink
        self.rewards = reward_sink or build_reward_sink(
            config, recorder.dir if recorder is not None else None
        )
        self.reward_count = 0
        self.reward_total = 0
        self.monitor.update(
            reward_mode=self.rewards.name,
            reward_policy=config.reward_policy,
            reward_count=0,
            reward_total=0,
        )

    # ------------------------------------------------------------------
    # session / block lifecycle
    # ------------------------------------------------------------------
    def session_open(
        self, now: float, *, psychopy_version: str, python_version: str
    ) -> None:
        self._event(
            "session_open",
            now,
            detail={"psychopy": psychopy_version, "python": python_version},
        )
        self.monitor.update(
            subject=self.cfg.subject,
            session_id=self.rec.session_id if self.rec else self.cfg.session_id,
            data_dir=str(self.rec.dir) if self.rec else "",
            config=self.cfg.to_dict(),
            grid={
                "rows": self.layout.rows,
                "cols": self.layout.cols,
                "left": self.layout.left,
                "top": self.layout.top,
                "pitch": self.layout.pitch,
                "line": self.layout.line,
            },
        )

    def instructions_end(self, now: float) -> None:
        self._event("instructions_end", now, detail={"skipped": False})

    def countdown_start(self, now: float) -> None:
        self._event("countdown_start", now)

    def run_start(self, now: float, block: int) -> None:
        if block == 1:
            self.markers.send(
                SESSION_START, t=now, detail={"subject": self.cfg.subject}
            )
            self._event(
                "run_start",
                now,
                detail={
                    "rows": self.cfg.rows,
                    "cols": self.cfg.cols,
                    "blocks": self.cfg.blocks,
                    "trials_per_block": self.cfg.targets,
                    "selection": self.cfg.selection,
                },
            )

    def block_start(self, now: float, block: int) -> None:
        self.markers.send(BLOCK_START, t=now, detail={"block": block})
        self._event(
            "block_start", now, detail={"block": block, "trials": self.cfg.targets}
        )

    def block_end(
        self, now: float, block: int, result: dict[str, Any], *, aborted: bool
    ) -> None:
        self.markers.send(
            BLOCK_END, t=now, detail={"block": block, "hits": result["hits"]}
        )
        self._event(
            "block_end",
            now,
            detail={
                "block": block,
                "aborted": aborted,
                "attempts": result["attempts"],
                "hits": result["hits"],
                "misclicks": result["misclicks"],
                "bps": round(result["bps"], 4),
            },
        )

    def rest_start(self, now: float) -> None:
        self._event("rest_start", now, detail={"seconds": self.cfg.block_rest})

    def iti_start(self, now: float, *, trial_index: int) -> None:
        self._event(
            "iti_start",
            now,
            target_index=trial_index,
            detail={"seconds": self.cfg.iti},
        )

    # ------------------------------------------------------------------
    # trials
    # ------------------------------------------------------------------
    def target_onset(
        self,
        now: float,
        *,
        block: int,
        target: Target,
        cursor_px: tuple[float, float],
    ) -> None:
        x_norm, y_norm = self.layout.px_to_norm(*cursor_px)
        self._event(
            "target_onset",
            now,
            x=x_norm,
            y=y_norm,
            cell=target.cell,
            target_index=target.index,
            detail={
                "onset": now,
                "selection": self.cfg.selection,
                "required_button": target.required_button,
            },
        )
        self.markers.send(
            TARGET_ONSET,
            t=now,
            detail={
                "block": block,
                "target_index": target.index,
                "row": target.cell.row + 1,
                "col": target.cell.col + 1,
                "required_button": target.required_button,
            },
        )

    def click(self, click: ClickEvent, *, target: Target | None) -> bool:
        """Record one click; return True when it counts as a misclick."""
        x_norm, y_norm = self.layout.px_to_norm(click.x_px, click.y_px)
        if self.cfg.selection == "dwell" and click.correct and click.button is None:
            name = "dwell_select"
        else:
            name = "click"
        self._event(
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
            return False
        if click.correct:
            return False
        self.markers.send(
            MISCLICK,
            t=click.time,
            detail={
                "button": click.button,
                "required_button": target.required_button if target else None,
            },
        )
        return True

    def trial(self, trial: TrialResult, *, block: int) -> None:
        self.monitor.add_trial(
            {
                "block": block,
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
            block,
            trial.index,
            self.cfg.targets,
            trial.outcome,
            trial.cell.label,
            trial.rt,
            trial.misclicks,
        )
        if self.rec is not None:
            self.rec.trial(trial)
        self._event(
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
                "block": block,
                "target_index": trial.index,
                "row": trial.cell.row + 1,
                "col": trial.cell.col + 1,
                "required_button": trial.required_button,
                "rt": round(trial.rt, 4),
            },
        )

    # ------------------------------------------------------------------
    # end of session
    # ------------------------------------------------------------------
    # reward
    # ------------------------------------------------------------------
    def reward(
        self,
        now: float,
        *,
        amount: int,
        duration_ms: int,
        reason: str = "hit",
        trial_index: int | None = None,
    ) -> None:
        """Deliver one reward pulse and record it everywhere.

        The strategy decides how the pulse leaves the machine; this method
        guarantees the CSV row, the marker/event trail and the panel counters
        stay consistent even when the hardware write fails.
        """
        if self.rewards.name == "off":
            # Nothing is delivered, so nothing is claimed in the data either.
            return
        self.rewards.deliver(amount, duration_ms, reason)
        self.reward_count += 1
        self.reward_total += int(amount)
        if self.rec is not None:
            self.rec.reward(
                now,
                amount=int(amount),
                duration_ms=int(duration_ms),
                reason=reason,
                trial_index=trial_index,
                sink=self.rewards.name,
            )
        self._event(
            "reward",
            now,
            target_index=trial_index,
            detail={
                "amount": int(amount),
                "duration_ms": int(duration_ms),
                "reason": reason,
                "sink": self.rewards.name,
            },
        )
        self.monitor.update(
            reward_mode=self.rewards.name,
            reward_count=self.reward_count,
            reward_total=self.reward_total,
        )

    # ------------------------------------------------------------------
    def session_end(self, now: float, summary: dict[str, Any], *, aborted: bool) -> None:
        if self.rec is not None:
            self.rec.write_summary(summary)
        self._event(
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
        # Setting phase=done is what tells the web panel that the end screen
        # is up (it uses that instant to close the LSL state stream).
        self.monitor.update(
            phase="done",
            aborted=bool(aborted),
            target=None,
            session_summary={
                key: summary[key]
                for key in (
                    "attempts",
                    "hits",
                    "misclicks",
                    "timeouts",
                    "bps",
                    "duration_s",
                )
            },
        )

    def close(self) -> None:
        try:
            self.markers.close()
        except Exception:  # noqa: BLE001 - teardown must not fail
            logger.exception("error closing event markers")
        try:
            if self._owns_reward_sink:
                self.rewards.close()
        except Exception:  # noqa: BLE001 - teardown must not fail
            logger.exception("error closing the reward sink")

    # ------------------------------------------------------------------
    def _event(
        self,
        name: str,
        now: float,
        *,
        x: float | None = None,
        y: float | None = None,
        button: int | None = None,
        cell: Any = None,
        target_index: int | None = None,
        detail: dict[str, Any] | str | None = None,
    ) -> None:
        if self.rec is None:
            return
        self.rec.event(
            name,
            now,
            x=x,
            y=y,
            button=button,
            cell=cell,
            target_index=target_index,
            detail=detail,
        )
