"""Scheduling strategies: per_hit / ratio / none."""

from __future__ import annotations

import pytest

from web_grid_paradigm.cli_args import build_parser, load_config
from web_grid_paradigm.core.config import ExperimentConfig
from web_grid_paradigm.core.session import Cell, TrialResult
from web_grid_paradigm.panel import form_schema
from web_grid_paradigm.reward.policy import (
    NoRewardPolicy,
    PerHitPolicy,
    RatioPolicy,
    build_reward_policy,
)


def make_trial(
    index: int = 1, *, correct: bool = True, offset: float = 1.0
) -> TrialResult:
    return TrialResult(
        index=index,
        cell=Cell(0, 0),
        required_button=1,
        onset=offset - 0.5,
        offset=offset,
        outcome="hit" if correct else "timeout",
        reason="click",
        correct=correct,
        rt=0.5,
        misclicks=0,
        button=1 if correct else None,
        path_px=10.0,
        straight_px=10.0,
        path_efficiency=1.0,
        dwell=False,
    )


def test_policy_selection() -> None:
    assert isinstance(build_reward_policy(ExperimentConfig()), PerHitPolicy)
    assert isinstance(
        build_reward_policy(ExperimentConfig(reward_policy="ratio")), RatioPolicy
    )
    assert isinstance(
        build_reward_policy(ExperimentConfig(reward_policy="none")), NoRewardPolicy
    )
    with pytest.raises(ValueError, match="unknown reward policy"):
        build_reward_policy(ExperimentConfig(reward_policy="bogus"))


def test_per_hit_policy_rewards_every_correct_trial() -> None:
    config = ExperimentConfig(reward_amount=3, reward_duration_ms=40)
    policy = build_reward_policy(config)
    hit = make_trial()
    miss = make_trial(correct=False)
    decision = policy.on_trial(hit, block=1, config=config)
    assert decision is not None
    assert (decision.amount, decision.duration_ms, decision.reason) == (3, 40, "hit")
    assert policy.on_trial(miss, block=1, config=config) is None
    zero = ExperimentConfig(reward_amount=0)
    assert build_reward_policy(zero).on_trial(hit, block=1, config=zero) is None


def test_ratio_policy_pays_every_nth_hit() -> None:
    config = ExperimentConfig(reward_policy="ratio", reward_ratio=2, reward_amount=1)
    policy = build_reward_policy(config)
    payouts = [
        policy.on_trial(make_trial(index=i), block=1, config=config) for i in range(1, 6)
    ]
    assert [p is not None for p in payouts] == [False, True, False, True, False]
    assert payouts[1].reason == "hit_fr2"
    # Misses do not advance the counter.
    policy.reset()
    policy.on_trial(make_trial(correct=False), block=1, config=config)
    assert policy.on_trial(make_trial(index=1), block=1, config=config) is None
    assert policy.on_trial(make_trial(index=2), block=1, config=config) is not None


def test_none_policy_never_rewards() -> None:
    config = ExperimentConfig(reward_policy="none")
    policy = build_reward_policy(config)
    assert policy.on_trial(make_trial(), block=1, config=config) is None


def test_policy_config_validation_and_cli() -> None:
    with pytest.raises(ValueError, match="reward_policy"):
        ExperimentConfig(reward_policy="magic").validate()
    with pytest.raises(ValueError, match="reward_ratio"):
        ExperimentConfig(reward_ratio=0).validate()
    parser = build_parser()
    config = load_config(
        parser.parse_args(["--reward-policy", "ratio", "--reward-ratio", "4"])
    )
    assert (config.reward_policy, config.reward_ratio) == ("ratio", 4)
    assert load_config(parser.parse_args([])).reward_policy == "per_hit"
    names = {field["name"] for field in form_schema()}
    assert {"reward_policy", "reward_ratio"} <= names
