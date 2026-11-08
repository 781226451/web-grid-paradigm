"""Recording side of rewards: rewards.csv, events.csv and the panel counters."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from web_grid_paradigm.cli_args import build_parser, load_config
from web_grid_paradigm.core.config import ExperimentConfig
from web_grid_paradigm.core.geometry import Layout
from web_grid_paradigm.panel import form_schema
from web_grid_paradigm.recorder import SessionRecorder
from web_grid_paradigm.reporter import Reporter
from web_grid_paradigm.reward.sink import DryRunRewardSink


def make_reporter(tmp_path: Path, **config: object) -> Reporter:
    cfg = ExperimentConfig(
        subject="sub-01", session="reward-test", output_dir=tmp_path / "data", **config
    )
    recorder = SessionRecorder(cfg)
    layout = Layout.create(800, 600, cfg.rows, cfg.cols)
    reporter = Reporter(
        cfg, layout, recorder=recorder, reward_sink=DryRunRewardSink(recorder.dir)
    )
    reporter.recorder = recorder  # convenience for the assertions below
    return reporter


def test_reporter_reward_writes_csv_event_and_counters(tmp_path: Path) -> None:
    reporter = make_reporter(tmp_path, reward_amount=2, reward_duration_ms=40)
    reporter.reward(1.5, amount=2, duration_ms=40, reason="hit", trial_index=3)
    reporter.reward(2.5, amount=2, duration_ms=40, reason="hit", trial_index=4)
    recorder = reporter.recorder

    with recorder.rewards_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert rows[0]["amount"] == "2"
    assert rows[0]["duration_ms"] == "40"
    assert rows[0]["reason"] == "hit"
    assert rows[0]["trial_index"] == "3"
    assert rows[0]["sink"] == "test"
    assert rows[0]["block"] == "1"

    with recorder.events_path.open(encoding="utf-8-sig", newline="") as handle:
        events = list(csv.DictReader(handle))
    rewards = [e for e in events if e["event"] == "reward"]
    assert len(rewards) == 2
    assert json.loads(rewards[0]["detail"])["amount"] == 2

    assert reporter.reward_count == 2
    assert reporter.reward_total == 4
    # The dry-run sink also wrote the wire bytes.
    assert (recorder.dir / "reward_out.txt").read_text(encoding="utf-8").count(
        "R 2 40"
    ) == 2
    recorder.close()


def test_reporter_without_recorder_still_delivers(tmp_path: Path) -> None:
    sink = DryRunRewardSink(tmp_path)
    reporter = Reporter(
        ExperimentConfig(reward="test"),
        Layout.create(800, 600, 4, 4),
        recorder=None,
        reward_sink=sink,
    )
    reporter.reward(0.5, amount=1, duration_ms=50)
    assert sink.sent == 1
    assert reporter.reward_total == 1


def test_off_sink_records_nothing(tmp_path: Path) -> None:
    """reward=off must not claim rewards in the data."""
    cfg = ExperimentConfig(
        subject="sub-01", session="off-test", output_dir=tmp_path / "data", reward="off"
    )
    recorder = SessionRecorder(cfg)
    reporter = Reporter(cfg, Layout.create(800, 600, 4, 4), recorder=recorder)
    reporter.reward(1.0, amount=5, duration_ms=50)
    with recorder.rewards_path.open(encoding="utf-8-sig", newline="") as handle:
        assert list(csv.DictReader(handle)) == []
    assert reporter.reward_count == 0
    recorder.close()


def test_shared_device_is_not_closed_by_the_session(tmp_path: Path) -> None:
    """A device connected from the panel survives the session that used it."""

    class Device:
        name = "serial"

        def __init__(self) -> None:
            self.closed = False
            self.delivered = 0

        def deliver(self, amount: int, duration_ms: int, reason: str = "") -> None:
            self.delivered += 1

        def close(self) -> None:
            self.closed = True

    device = Device()
    reporter = Reporter(
        ExperimentConfig(reward="serial"),
        Layout.create(800, 600, 4, 4),
        recorder=None,
        reward_sink=device,
        own_reward_sink=False,
    )
    reporter.reward(1.0, amount=1, duration_ms=50)
    reporter.close()
    assert device.delivered == 1
    assert device.closed is False


# ---------------------------------------------------------------- wiring
def test_reward_config_validation() -> None:
    ExperimentConfig(reward="test").validate()
    with pytest.raises(ValueError, match="reward must be"):
        ExperimentConfig(reward="magic").validate()
    with pytest.raises(ValueError, match="reward_amount"):
        ExperimentConfig(reward="test", reward_amount=999).validate()

    with pytest.raises(ValueError, match="reward_port"):
        ExperimentConfig(reward="serial", reward_port="  ").validate()


def test_cli_and_form_expose_reward_options() -> None:
    parser = build_parser()
    config = load_config(
        parser.parse_args(
            ["--reward", "test", "--reward-amount", "3", "--reward-duration-ms", "80"]
        )
    )
    assert (config.reward, config.reward_amount, config.reward_duration_ms) == (
        "test",
        3,
        80,
    )
    assert load_config(parser.parse_args([])).reward == "serial"
    names = {field["name"] for field in form_schema()}
    # The panel exposes the reward choices and schedule; port, baud rate and
    # the command template belong to the device dialog / TOML file.
    assert {
        "reward",
        "reward_policy",
        "reward_amount",
        "reward_duration_ms",
    } <= names
    assert {"reward_port", "reward_baud"}.isdisjoint(names)
