"""Reward scheduling — the *when* module.

Decides when a reward is due and how much it carries.  It knows nothing about
serial ports, files or any other transport: it returns a :class:`Reward`
decision and the caller hands that to whatever delivery module is configured.

Policies are pure: they see the finished trial, return a ``Reward`` or
``None``, and keep any counters themselves (``reset()`` is called per session).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..core.config import ExperimentConfig
from ..core.session import TrialResult


@dataclass(frozen=True, slots=True)
class Reward:
    """One reward decision: what to deliver if the trial qualifies."""

    amount: int
    duration_ms: int
    reason: str


class RewardPolicy(Protocol):
    """Strategy interface for *when* to reward."""

    name: str

    def reset(self) -> None: ...

    def on_trial(
        self, trial: TrialResult, *, block: int, config: ExperimentConfig
    ) -> Reward | None: ...


class NoRewardPolicy:
    """Never reward (behaviour-only sessions)."""

    name = "none"

    def reset(self) -> None:
        return None

    def on_trial(
        self, trial: TrialResult, *, block: int, config: ExperimentConfig
    ) -> Reward | None:
        return None


class PerHitPolicy:
    """Continuous reward: every correct trial pays out (default)."""

    name = "per_hit"

    def reset(self) -> None:
        return None

    def on_trial(
        self, trial: TrialResult, *, block: int, config: ExperimentConfig
    ) -> Reward | None:
        if not trial.correct or config.reward_amount <= 0:
            return None
        return Reward(
            amount=config.reward_amount,
            duration_ms=config.reward_duration_ms,
            reason="hit",
        )


class RatioPolicy:
    """Fixed-ratio schedule: pay out every ``reward_ratio``-th hit (FR-n)."""

    name = "ratio"

    def __init__(self) -> None:
        self._hits = 0

    def reset(self) -> None:
        self._hits = 0

    @property
    def hits(self) -> int:
        return self._hits

    def on_trial(
        self, trial: TrialResult, *, block: int, config: ExperimentConfig
    ) -> Reward | None:
        if not trial.correct or config.reward_amount <= 0:
            return None
        self._hits += 1
        ratio = max(1, int(config.reward_ratio))
        if self._hits % ratio:
            return None
        return Reward(
            amount=config.reward_amount,
            duration_ms=config.reward_duration_ms,
            reason=f"hit_fr{ratio}",
        )


POLICIES: dict[str, type[RewardPolicy]] = {
    "per_hit": PerHitPolicy,
    "ratio": RatioPolicy,
    "none": NoRewardPolicy,
}


def build_reward_policy(config: ExperimentConfig) -> RewardPolicy:
    """Instantiate the schedule named in the configuration."""
    try:
        factory = POLICIES[config.reward_policy]
    except KeyError as exc:
        raise ValueError(f"unknown reward policy: {config.reward_policy!r}") from exc
    return factory()
