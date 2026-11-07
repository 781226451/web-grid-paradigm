"""Reward hardware configuration file, port discovery and the panel self-test."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pytest

from web_grid_paradigm.cli_args import (
    apply_reward_config,
    build_parser,
    load_config,
)
from web_grid_paradigm.config import ExperimentConfig
from web_grid_paradigm.panel import Station
from web_grid_paradigm.reward.sink import serial_ports


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------- reward TOML
def test_reward_config_file_overrides_defaults(tmp_path: Path) -> None:
    path = write(
        tmp_path / "reward.toml",
        'reward = "test"\nreward_port = "COM7"\nreward_baud = 115200\n'
        "reward_amount = 3\n",
    )
    base = ExperimentConfig()
    config = apply_reward_config(base, path)
    assert config.reward == "test"
    assert config.reward_port == "COM7"
    assert config.reward_baud == 115200
    assert config.reward_amount == 3
    # Unrelated settings are untouched.
    assert config.rows == base.rows


def test_reward_config_accepts_a_table_and_rejects_unknown_keys(tmp_path: Path) -> None:
    table = write(
        tmp_path / "reward.toml",
        '[reward]\nreward_port = "COM9"\nreward_duration_ms = 80\n',
    )
    config = apply_reward_config(ExperimentConfig(), table)
    assert (config.reward_port, config.reward_duration_ms) == ("COM9", 80)

    bad = write(tmp_path / "bad.toml", 'rows = 4\nreward_port = "COM1"\n')
    with pytest.raises(ValueError, match="unknown reward key"):
        apply_reward_config(ExperimentConfig(), bad)


def test_single_config_file_can_hold_a_reward_section(tmp_path: Path) -> None:
    """One TOML is enough: paradigm keys plus a [reward] table."""
    path = write(
        tmp_path / "session.toml",
        "subject = 'sub-07'\nrows = 8\ncols = 10\n\n"
        "[reward]\nreward_port = 'COM11'\nreward_policy = 'ratio'\n",
    )
    config = ExperimentConfig.from_toml(path)
    assert (config.subject, config.rows, config.cols) == ("sub-07", 8, 10)
    assert (config.reward_port, config.reward_policy) == ("COM11", "ratio")


def test_nested_reward_section_under_webgrid(tmp_path: Path) -> None:
    path = write(
        tmp_path / "session.toml",
        "[webgrid]\nrows = 6\n\n[webgrid.reward]\nreward_port = 'COM5'\n",
    )
    config = ExperimentConfig.from_toml(path)
    assert (config.rows, config.reward_port) == (6, "COM5")


def test_cli_reward_config_and_precedence(tmp_path: Path) -> None:
    path = write(
        tmp_path / "reward.toml", 'reward = "test"\nreward_port = "COM5"\n'
    )
    parser = build_parser()
    config = load_config(parser.parse_args(["--reward-config", str(path)]))
    assert (config.reward, config.reward_port) == ("test", "COM5")
    # Command line still wins over the file.
    config = load_config(
        parser.parse_args(["--reward-config", str(path), "--reward", "off"])
    )
    assert config.reward == "off"


def test_missing_reward_config_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        apply_reward_config(ExperimentConfig(), tmp_path / "nope.toml")


# ---------------------------------------------------------------- port list
def test_serial_ports_lists_devices(monkeypatch: pytest.MonkeyPatch) -> None:
    class Port:
        def __init__(self, device: str, description: str) -> None:
            self.device = device
            self.description = description

    from serial.tools import list_ports

    monkeypatch.setattr(
        list_ports,
        "comports",
        lambda: [Port("COM3", "USB-SERIAL CH340"), Port("COM9", "")],
    )
    ports = serial_ports()
    assert [p["device"] for p in ports] == ["COM3", "COM9"]
    assert ports[0]["description"] == "USB-SERIAL CH340"


def test_serial_ports_survives_driver_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    from serial.tools import list_ports

    def boom() -> list[object]:
        raise OSError("driver exploded")

    monkeypatch.setattr(list_ports, "comports", boom)
    assert serial_ports() == []


# ---------------------------------------------------------------- self-test
@pytest.fixture
def station(tmp_path: Path):
    board = Station(
        "127.0.0.1", 0, base_config=ExperimentConfig(), open_browser=False
    )
    yield board
    board.close()


def _url(station: Station, path: str) -> str:
    return f"http://127.0.0.1:{station.port}{path}"


def test_config_endpoint_exposes_serial_ports(
    station: Station, monkeypatch: pytest.MonkeyPatch
) -> None:
    from serial.tools import list_ports

    class Port:
        device = "COM4"
        description = "Arduino Uno"

    monkeypatch.setattr(list_ports, "comports", lambda: [Port()])
    with urllib.request.urlopen(_url(station, "/api/config"), timeout=5) as response:
        payload = json.loads(response.read())
    assert payload["options"]["reward_port"][0]["device"] == "COM4"


def _post(station: Station, path: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode()
    request = urllib.request.Request(
        _url(station, path), data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_reward_self_test_in_dry_run_mode(station: Station) -> None:
    status, payload = _post(
        station,
        "/api/reward/test",
        {"reward": "test", "reward_amount": 2, "reward_duration_ms": 40},
    )
    assert status == 200
    assert payload["sink"] == "test"
    assert payload["command"] == "R 2 40"


class FakePort:
    """Stands in for pyserial's Serial in the panel tests."""

    def __init__(self) -> None:
        self.written: list[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> int:
        self.written.append(data)
        return len(data)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def test_reward_connect_reports_a_closed_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    board = Station(
        "127.0.0.1",
        0,
        base_config=ExperimentConfig(reward="serial", reward_port="COM42"),
        open_browser=False,
    )
    try:
        def boom(*_a: object, **_k: object) -> None:
            raise OSError("port busy")

        monkeypatch.setattr("web_grid_paradigm.reward.sink._open_serial", boom)
        status, payload = _post(
            board, "/api/reward/connect", {"port": "COM42", "baud": 9600}
        )
        assert status == 400
        assert "COM42" in payload["error"]
        assert board.reward_status()["connected"] is False
    finally:
        board.close()


def test_reward_connect_disconnect_and_self_test(
    station: Station, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = FakePort()
    monkeypatch.setattr("web_grid_paradigm.reward.sink._open_serial", lambda *a, **k: port)

    status, payload = _post(
        station, "/api/reward/connect", {"port": "COM_TEST", "baud": 115200}
    )
    assert status == 200
    assert payload["connected"] is True
    assert (payload["port"], payload["baud"]) == ("COM_TEST", 115200)
    assert station.reward_device() is not None

    # The self-test goes through the connected device with the built-in command.
    status, payload = _post(
        station,
        "/api/reward/test",
        {"reward": "serial", "reward_amount": 2, "reward_duration_ms": 40},
    )
    assert status == 200
    assert payload["port"] == "COM_TEST"
    assert payload["command"] == "R 2 40"
    assert port.written == [b"R 2 40\n"]

    status, payload = _post(station, "/api/reward/disconnect", {})
    assert status == 200
    assert payload["connected"] is False
    assert port.closed is True
    assert station.reward_device() is None


def test_reward_connect_rejects_a_bad_baud_rate(station: Station) -> None:
    status, payload = _post(
        station, "/api/reward/connect", {"port": "COM_TEST", "baud": 12}
    )
    assert status == 400
    assert "波特率" in payload["error"]


def test_reward_self_test_needs_a_connection(station: Station) -> None:
    status, payload = _post(station, "/api/reward/test", {"reward": "serial"})
    assert status == 400
    assert "未连接" in payload["error"]


def test_reward_panel_has_no_port_or_baud_fields(station: Station) -> None:
    """Port and baud rate are configured in TOML, not in the web UI."""
    with urllib.request.urlopen(_url(station, "/api/config"), timeout=5) as response:
        payload = json.loads(response.read())
    names = {field["name"] for field in payload["schema"]}
    assert "reward_port" not in names
    assert "reward_baud" not in names
    # The detected ports are still exposed, as read-only information.
    assert "reward_port" in payload["options"]


def test_reward_self_test_with_rewards_off(station: Station) -> None:
    status, payload = _post(station, "/api/reward/test", {"reward": "off"})
    assert status == 200
    assert payload["sink"] == "off"
