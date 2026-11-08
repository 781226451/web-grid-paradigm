"""Delivery strategies: serial / dry-run / off."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from web_grid_paradigm.core.config import ExperimentConfig
from web_grid_paradigm.reward.sink import (
    DryRunRewardSink,
    NullRewardSink,
    SerialRewardSink,
    build_reward_sink,
    format_command,
)


def test_format_command_default_protocol() -> None:
    assert format_command(2, 40) == "R 2 40\n"


def test_build_reward_sink_selects_strategy(tmp_path: Path) -> None:
    assert isinstance(
        build_reward_sink(ExperimentConfig(reward="off"), tmp_path), NullRewardSink
    )
    sink = build_reward_sink(ExperimentConfig(reward="test"), tmp_path)
    assert isinstance(sink, DryRunRewardSink)
    with pytest.raises(ValueError, match="unknown reward mode"):
        build_reward_sink(ExperimentConfig(reward="bogus"), tmp_path)


def test_dry_run_sink_records_exact_bytes(tmp_path: Path) -> None:
    sink = build_reward_sink(ExperimentConfig(reward="test"), tmp_path)
    sink.deliver(1, 50, "hit")
    sink.deliver(3, 20, "hit")
    sink.close()
    assert (tmp_path / "reward_out.txt").read_text(encoding="utf-8") == (
        "R 1 50\nR 3 20\n"
    )
    assert sink.sent == 2


class FakeSerial:
    """Records what would be written to the Arduino."""

    def __init__(self) -> None:
        self.written: list[bytes] = []
        self.closed = False
        self.release = threading.Event()

    def write(self, data: bytes) -> int:
        self.release.wait(2)
        self.written.append(data)
        return len(data)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_serial(monkeypatch: pytest.MonkeyPatch) -> FakeSerial:
    fake = FakeSerial()
    monkeypatch.setattr(
        "web_grid_paradigm.reward.sink._open_serial", lambda *a, **k: fake, raising=True
    )
    return fake


def test_serial_sink_writes_ascii_command(fake_serial: FakeSerial) -> None:
    sink = SerialRewardSink("COM_TEST", 9600)
    sink.deliver(2, 30, "hit")
    fake_serial.release.set()
    deadline = time.time() + 5
    while not fake_serial.written and time.time() < deadline:
        time.sleep(0.01)
    sink.close()
    assert fake_serial.written == [b"R 2 30\n"]
    assert fake_serial.closed is True


def test_serial_failure_falls_back_to_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise OSError("port busy")

    monkeypatch.setattr("web_grid_paradigm.reward.sink._open_serial", boom)
    sink = build_reward_sink(ExperimentConfig(reward="serial"), tmp_path)
    assert isinstance(sink, DryRunRewardSink)
    sink.deliver(1, 50)
    assert (tmp_path / "reward_out.txt").exists()
