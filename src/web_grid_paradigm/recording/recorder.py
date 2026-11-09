"""Session data files: config snapshot, event log, trial table and summary."""

from __future__ import annotations

import csv
import json
import platform
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from ..core.config import ExperimentConfig
from ..core.geometry import Cell
from ..core.session import TrialResult

_EVENT_FIELDS = [
    "subject",
    "session_id",
    "utc",
    "monotonic_s",
    "event",
    "block",
    "target_index",
    "cell",
    "row",
    "col",
    "x_norm",
    "y_norm",
    "button",
    "detail",
]

_TRIAL_FIELDS = [
    "subject",
    "session_id",
    "block",
    "trial_index",
    "target_cell",
    "target_row",
    "target_col",
    "required_button",
    "onset_s",
    "offset_s",
    "rt_s",
    "outcome",
    "reason",
    "correct",
    "misclicks",
    "button",
    "path_px",
    "straight_px",
    "path_efficiency",
    "dwell",
]


_REWARD_FIELDS = [
    "subject",
    "session_id",
    "block",
    "trial_index",
    "utc",
    "monotonic_s",
    "amount",
    "duration_ms",
    "reason",
    "sink",
]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class SessionRecorder:
    """Writes one self-contained directory per session."""

    def __init__(
        self,
        config: ExperimentConfig,
        *,
        psychopy_version: str = "",
        session_id: str | None = None,
        created_utc: str | None = None,
        sources: Mapping[str, str] | None = None,
        config_files: Mapping[str, str] | None = None,
    ) -> None:
        self.config = config
        self.sources = dict(sources or {})
        self.config_files = dict(config_files or {})
        self.session_id = session_id or config.session_id
        self.start_utc = created_utc or _utc_now()
        self.dir = self._allocate_dir(
            config.output_dir / config.subject / f"ses-{self.session_id}"
        )
        self.dir.mkdir(parents=True, exist_ok=False)

        meta = {
            "session_id": self.session_id,
            "created_utc": self.start_utc,
            "python_version": sys.version,
            "psychopy_version": psychopy_version,
            "platform": platform.platform(),
            "config": config.to_dict(),
            "config_sources": self.sources,
            "config_files": self.config_files,
        }
        (self.dir / "config.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        self.events_path = self.dir / "events.csv"
        self.trials_path = self.dir / "trials.csv"
        self.rewards_path = self.dir / "rewards.csv"
        self.summary_path = self.dir / "summary.json"

        self._events_file = self.events_path.open("w", newline="", encoding="utf-8-sig")
        self._trials_file = self.trials_path.open("w", newline="", encoding="utf-8-sig")
        self._rewards_file = self.rewards_path.open(
            "w", newline="", encoding="utf-8-sig"
        )
        self._events = csv.DictWriter(self._events_file, fieldnames=_EVENT_FIELDS)
        self._trials = csv.DictWriter(self._trials_file, fieldnames=_TRIAL_FIELDS)
        self._rewards = csv.DictWriter(self._rewards_file, fieldnames=_REWARD_FIELDS)
        self._events.writeheader()
        self._trials.writeheader()
        self._rewards.writeheader()
        self._events_file.flush()
        self._trials_file.flush()
        self._rewards_file.flush()
        self._closed = False
        self.closed_utc = ""
        self.block = 1  # current block, written into every row

    @staticmethod
    def _allocate_dir(preferred: Path) -> Path:
        if not preferred.exists():
            return preferred
        for index in range(2, 1000):
            candidate = preferred.with_name(f"{preferred.name}-{index}")
            if not candidate.exists():
                return candidate
        raise RuntimeError(
            f"could not allocate a session directory next to {preferred}"
        )

    # ------------------------------------------------------------------
    def event(
        self,
        name: str,
        t: float,
        *,
        x: float | None = None,
        y: float | None = None,
        button: int | None = None,
        cell: Cell | None = None,
        target_index: int | None = None,
        detail: dict[str, Any] | str | None = None,
    ) -> None:
        if self._closed:
            return
        if isinstance(detail, dict):
            detail_text = json.dumps(detail, ensure_ascii=False)
        else:
            detail_text = detail or ""
        self._events.writerow(
            {
                "subject": self.config.subject,
                "session_id": self.session_id,
                "utc": _utc_now(),
                "monotonic_s": f"{t:.6f}",
                "event": name,
                "block": self.block,
                "target_index": target_index if target_index is not None else "",
                "cell": cell.label if cell else "",
                "row": cell.row + 1 if cell else "",
                "col": cell.col + 1 if cell else "",
                "x_norm": f"{x:.6f}" if x is not None else "",
                "y_norm": f"{y:.6f}" if y is not None else "",
                "button": button if button is not None else "",
                "detail": detail_text,
            }
        )
        self._events_file.flush()

    def trial(self, result: TrialResult) -> None:
        if self._closed:
            return
        self._trials.writerow(
            {
                "subject": self.config.subject,
                "session_id": self.session_id,
                "block": self.block,
                "trial_index": result.index,
                "target_cell": result.cell.label,
                "target_row": result.cell.row + 1,
                "target_col": result.cell.col + 1,
                "required_button": result.required_button,
                "onset_s": f"{result.onset:.6f}",
                "offset_s": f"{result.offset:.6f}",
                "rt_s": f"{result.rt:.6f}",
                "outcome": result.outcome,
                "reason": result.reason,
                "correct": int(result.correct),
                "misclicks": result.misclicks,
                "button": result.button if result.button is not None else "",
                "path_px": f"{result.path_px:.3f}",
                "straight_px": f"{result.straight_px:.3f}",
                "path_efficiency": (
                    f"{result.path_efficiency:.6f}"
                    if result.path_efficiency is not None
                    else ""
                ),
                "dwell": int(result.dwell),
            }
        )
        self._trials_file.flush()

    def reward(
        self,
        t: float,
        *,
        amount: int,
        duration_ms: int,
        reason: str = "",
        trial_index: int | None = None,
        sink: str = "",
    ) -> None:
        """One row per delivered reward pulse."""
        if self._closed:
            return
        self._rewards.writerow(
            {
                "subject": self.config.subject,
                "session_id": self.session_id,
                "block": self.block,
                "trial_index": trial_index if trial_index is not None else "",
                "utc": _utc_now(),
                "monotonic_s": f"{t:.6f}",
                "amount": amount,
                "duration_ms": duration_ms,
                "reason": reason,
                "sink": sink,
            }
        )
        self._rewards_file.flush()

    def write_summary(self, summary: dict[str, Any]) -> Path:
        self.closed_utc = _utc_now()
        payload = {
            "session_id": self.session_id,
            "created_utc": self.start_utc,
            "closed_utc": self.closed_utc,
            "config": self.config.to_dict(),
            "results": summary,
        }
        self._write_json(self.summary_path, payload)
        return self.summary_path

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._events_file.close()
        self._trials_file.close()
        self._rewards_file.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
