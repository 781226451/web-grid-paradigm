from __future__ import annotations

import io
import json
import threading
import time
import tomllib
import urllib.error
import urllib.request
import zipfile

import pytest

from web_grid_paradigm.app.cli_args import build_parser, load_config
from web_grid_paradigm.core.config import ExperimentConfig
from web_grid_paradigm.core.monitor import NullMonitor
from web_grid_paradigm.core.settings import FIELD_SCOPES, SCOPE_BOOTSTRAP
from web_grid_paradigm.panel import (
    SessionView,
    coerce_params,
    form_schema,
    start_station,
)


def make_station(**kwargs) -> Station:  # noqa: F821 - imported lazily below
    from web_grid_paradigm.panel import Station

    station = Station("127.0.0.1", 0, **kwargs)
    station.attach_logs()
    return station


@pytest.fixture
def station():
    board = make_station(open_browser=False)
    yield board
    board.close()


def _url(station, path: str) -> str:
    return f"http://127.0.0.1:{station.port}{path}"


def _get(station, path: str) -> tuple[int, dict]:
    with urllib.request.urlopen(_url(station, path), timeout=5) as response:
        return response.status, json.loads(response.read())


def _post(station, path: str, payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload or {}).encode()
    request = urllib.request.Request(
        _url(station, path), data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _post_bytes(
    station, path: str, payload: dict | None = None
) -> tuple[int, dict, bytes]:
    """POST and return the raw body (for downloads that are not JSON)."""
    data = json.dumps(payload or {}).encode()
    request = urllib.request.Request(
        _url(station, path), data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


# ---------------------------------------------------------------- parameters
def test_form_schema_matches_config_fields() -> None:
    names = {field["name"] for field in form_schema()}
    config_fields = set(ExperimentConfig().to_dict())
    assert names <= config_fields, names - config_fields
    for field in form_schema():
        assert field["name"] in FIELD_SCOPES
        assert FIELD_SCOPES[field["name"]] != SCOPE_BOOTSTRAP
    for required in ("blocks", "targets", "rows", "cols", "iti"):
        assert required in names
    # The LSL start-command trigger has been removed.
    assert not {"wait_start", "start_stream", "start_command"} & names
    assert not {"wait_start", "start_stream", "start_command"} & config_fields


def test_coerce_params_validates_and_passes_through() -> None:
    base = ExperimentConfig(demo_speed=3.5, subject="base")
    config = coerce_params(
        {"blocks": "3", "targets": 20, "rows": 8, "cols": 10, "fullscreen": False},
        base,
    )
    assert (config.blocks, config.targets, config.rows, config.cols) == (3, 20, 8, 10)
    assert config.fullscreen is False
    assert config.demo_speed == 3.5  # untouched fields come from the base
    assert config.subject == "base"

    with pytest.raises(ValueError, match="未知参数"):
        coerce_params({"nope": 1}, base)
    with pytest.raises(ValueError, match="rows"):
        coerce_params({"rows": 1}, base)
    with pytest.raises(ValueError, match="选择方式"):
        coerce_params({"selection": "telepathy"}, base)


# ---------------------------------------------------------------- HTTP API
def test_config_endpoint_returns_schema_and_values(station) -> None:
    status, payload = _get(station, "/api/config")
    assert status == 200
    assert payload["control"] is True
    assert payload["values"]["blocks"] == station.base_config.blocks
    assert any(f["name"] == "targets" for f in payload["schema"])
    assert payload["sources"]["blocks"] == "default"
    assert payload["scopes"]["blocks"] == "experiment"
    assert payload["editable"]["blocks"] is True


def test_config_endpoint_reports_startup_source() -> None:
    board = make_station(
        base_config=ExperimentConfig(rows=8),
        base_sources={"rows": "cli"},
        open_browser=False,
    )
    try:
        _, payload = _get(board, "/api/config")
        assert payload["values"]["rows"] == 8
        assert payload["sources"]["rows"] == "cli"
        assert payload["sources"]["cols"] == "default"
    finally:
        board.close()


def test_config_endpoint_reports_source_files() -> None:
    board = make_station(
        base_config=ExperimentConfig(joystick_port="COM4"),
        base_sources={"joystick_port": "device"},
        base_config_files={"joystick_port": "configs/velocity_input.toml"},
        open_browser=False,
    )
    try:
        _, payload = _get(board, "/api/config")
        assert payload["sources"]["joystick_port"] == "device"
        assert (
            payload["source_files"]["joystick_port"]
            == "configs/velocity_input.toml"
        )
        assert payload["source_files"]["rows"] is None
    finally:
        board.close()


def test_page_is_served(station) -> None:
    with urllib.request.urlopen(_url(station, "/"), timeout=5) as response:
        body = response.read().decode("utf-8")
    assert response.status == 200
    assert "BCI Web-Grid" in body
    assert "/assets/" in body




def test_start_rejects_bad_parameters(station) -> None:
    status, payload = _post(station, "/api/start", {"rows": 1})
    assert status == 400
    assert "rows" in payload["error"]
    status, payload = _post(station, "/api/start", {"bogus": True})
    assert status == 400 and "未知参数" in payload["error"]


def test_start_rejects_bootstrap_fields(station) -> None:
    status, payload = _post(station, "/api/start", {"dashboard_port": 9000})
    assert status == 400
    assert "启动参数" in payload["error"]


def test_start_queues_a_validated_run(station) -> None:
    status, payload = _post(
        station, "/api/start", {"blocks": 2, "targets": 5, "rows": 6, "cols": 6}
    )
    assert status == 200 and payload["ok"] is True
    assert payload["config"]["blocks"] == 2
    # The queued request is what serve() will pick up first.
    request = station._next_request()
    assert request is not None
    config, source, sources, files = request
    assert (config.blocks, config.targets, source) == (2, 5, "web")
    assert sources["blocks"] == "webui"
    assert sources["dashboard_host"] == "default"
    assert files == {}


def test_webui_source_marks_only_changed_fields() -> None:
    board = make_station(
        base_config=ExperimentConfig(rows=8),
        base_sources={"rows": "cli"},
        open_browser=False,
    )
    try:
        status, _ = _post(board, "/api/start", {"rows": 8, "cols": 9})
        assert status == 200
        request = board._next_request()
        assert request is not None
        _, _, sources, _ = request
        assert sources["rows"] == "cli"
        assert sources["cols"] == "webui"
    finally:
        board.close()


def test_webui_device_edit_drops_file_provenance() -> None:
    board = make_station(
        base_config=ExperimentConfig(joystick_port="COM4"),
        base_sources={"joystick_port": "device"},
        base_config_files={"joystick_port": "configs/velocity_input.toml"},
        open_browser=False,
    )
    try:
        status, _ = _post(board, "/api/start", {"joystick_port": "COM9"})
        assert status == 200
        request = board._next_request()
        assert request is not None
        _, _, sources, files = request
        assert sources["joystick_port"] == "webui"
        assert "joystick_port" not in files
    finally:
        board.close()


def test_webui_unchanged_device_field_keeps_file_provenance() -> None:
    board = make_station(
        base_config=ExperimentConfig(joystick_port="COM4"),
        base_sources={"joystick_port": "device"},
        base_config_files={"joystick_port": "configs/velocity_input.toml"},
        open_browser=False,
    )
    try:
        status, _ = _post(board, "/api/start", {"joystick_port": "COM4"})
        assert status == 200
        request = board._next_request()
        assert request is not None
        _, _, sources, files = request
        assert sources["joystick_port"] == "device"
        assert files == {"joystick_port": "configs/velocity_input.toml"}
    finally:
        board.close()


# ------------------------------------------------- configuration export
def test_config_export_returns_a_zip_attachment(station) -> None:
    status, headers, body = _post_bytes(
        station, "/api/config/export", {"subject": "web-export", "rows": 8}
    )
    assert status == 200
    assert headers["Content-Type"] == "application/zip"
    assert headers["Content-Disposition"].startswith(
        'attachment; filename="webgrid-config-web-export-'
    )
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        root = archive.namelist()[0].split("/", 1)[0]
        config_toml = archive.read(f"{root}/config.toml").decode("utf-8")
        device_toml = archive.read(f"{root}/velocity_input.toml").decode("utf-8")
        snapshot = json.loads(archive.read(f"{root}/config.json"))
    assert 'subject = "web-export"' in config_toml
    assert "rows = 8" in config_toml
    assert snapshot["config"]["subject"] == "web-export"
    assert snapshot["config_sources"]["subject"] == "webui"
    assert snapshot["config_sources"]["cols"] == "default"
    # Device modules are written even when the input mode is not joystick.
    assert "joystick_port" in device_toml


def test_config_export_rejects_invalid_values(station) -> None:
    status, payload = _post(station, "/api/config/export", {"rows": 1})
    assert status == 400 and "rows" in payload["error"]
    status, payload = _post(station, "/api/config/export", {"bogus": True})
    assert status == 400 and "未知参数" in payload["error"]


def test_config_export_captures_panel_level_settings() -> None:
    board = make_station(open_browser=False)
    try:
        board.start_lsl_state("RigState", 20)
        with board._cond:
            board._reward_port = "COM9"
            board._reward_baud = 19200
        status, _, body = _post_bytes(board, "/api/config/export", {})
        assert status == 200
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            root = archive.namelist()[0].split("/", 1)[0]
            lsl = tomllib.loads(
                archive.read(f"{root}/lsl_outputs.toml").decode("utf-8")
            )
            reward = tomllib.loads(
                archive.read(f"{root}/reward.toml").decode("utf-8")
            )
            snapshot = json.loads(archive.read(f"{root}/config.json"))
        assert (lsl["lsl_state"], lsl["lsl_state_stream"]) == (True, "RigState")
        assert lsl["lsl_state_rate"] == 20.0
        assert (reward["reward_port"], reward["reward_baud"]) == ("COM9", 19200)
        assert snapshot["config_sources"]["lsl_state"] == "webui"
        assert snapshot["config_sources"]["reward_port"] == "webui"
    finally:
        board.close()


def test_readonly_panel_can_export() -> None:
    board = make_station(control=False, open_browser=False)
    try:
        status, _, body = _post_bytes(board, "/api/config/export", {"rows": 6})
        assert status == 200 and body.startswith(b"PK")
    finally:
        board.close()


def test_session_view_exposes_config_files(station) -> None:
    station._begin_run(
        ExperimentConfig(blocks=1, targets=1),
        "test",
        config_files={"joystick_port": "configs/velocity_input.toml"},
    )
    run_id = station._current["id"]
    view = SessionView(station, run_id)
    assert view.config_files == {
        "joystick_port": "configs/velocity_input.toml"
    }
    station._end_run(run_id, "finished")


def test_stop_before_start_does_nothing(station) -> None:
    assert station.request_stop() is False


# ---------------------------------------------------------------- run loop
def test_serve_runs_a_session_and_records_it(station) -> None:
    seen: dict[str, object] = {}

    def fake_run(config, view):
        seen["config"] = config
        assert isinstance(view, SessionView)
        view.update(phase="run", block=1, trials_done=1, config=config.to_dict())
        view.add_trial({"block": 1, "trial": 1, "outcome": "hit", "rt": 0.5,
                        "misclicks": 0, "cell": "r2c2", "path_efficiency": 1.0})
        view.cursor(10.0, 20.0, fps=60.0)
        view.set_blocks([{"block": 1, "attempts": 1, "hits": 1, "misclicks": 0,
                          "bps": 1.0, "mean_rt_s": 0.5, "aborted": False}])
        assert view.stop_requested is False
        return {"attempts": 1, "hits": 1, "misclicks": 0, "timeouts": 0,
                "bps": 1.0, "duration_s": 5.0}

    station.request_start(
        ExperimentConfig(subject="s1", blocks=1, targets=1, rows=4, cols=4), "test"
    )

    thread = threading.Thread(target=station.serve, args=(fake_run,), daemon=True)
    thread.start()
    deadline = time.time() + 10
    while time.time() < deadline and not station._runs:
        time.sleep(0.02)
    # serve() keeps waiting for the next run by design; the thread is a daemon.

    assert seen["config"].subject == "s1"
    _, payload = _get(station, "/api/state")
    assert payload["status"] == "idle"
    assert payload["state"]["phase"] == "done"
    assert payload["trials"][0]["outcome"] == "hit"
    assert payload["runs"][0]["status"] == "finished"
    assert payload["runs"][0]["hits"] == 1
    assert payload["runs"][0]["bps"] == 1.0


def test_failure_is_recorded_and_the_panel_survives(station) -> None:
    def boom(config, view):
        raise RuntimeError("psychopy exploded")

    station.request_start(ExperimentConfig(blocks=1, targets=1), "test")
    thread = threading.Thread(target=station.serve, args=(boom,), daemon=True)
    thread.start()
    deadline = time.time() + 10
    while time.time() < deadline and not station._runs:
        time.sleep(0.02)
    # serve() keeps waiting for the next run by design; the thread is a daemon.

    _, payload = _get(station, "/api/state")
    assert payload["runs"][0]["status"] == "failed"
    assert "psychopy exploded" in payload["runs"][0]["error"]
    assert payload["status"] == "idle"  # ready for the next run


def test_stop_request_reaches_the_view(station) -> None:
    stop_seen = threading.Event()

    def long_run(config, view):
        for _ in range(500):
            if view.stop_requested:
                stop_seen.set()
                return {"attempts": 0, "hits": 0, "misclicks": 0, "timeouts": 0,
                        "bps": 0.0, "duration_s": 0.0}
            time.sleep(0.01)
        return {}

    station.request_start(ExperimentConfig(), "test")
    thread = threading.Thread(target=station.serve, args=(long_run,), daemon=True)
    thread.start()
    for _ in range(100):
        if station._status == "running":
            break
        time.sleep(0.02)
    assert _post(station, "/api/stop")[1]["stopping"] is True
    assert stop_seen.wait(5)
    # serve() keeps waiting for the next run by design; the thread is a daemon.


def test_readonly_station_refuses_start() -> None:
    board = make_station(control=False, open_browser=False)
    try:
        status, payload = _post(board, "/api/start", {"blocks": 1})
        assert status == 409 and "只读" in payload["error"]
    finally:
        board.close()


def test_port_in_use_falls_back(station) -> None:
    assert start_station("127.0.0.1", station.port) is None


def test_null_monitor_is_inert() -> None:
    view = NullMonitor()
    view.update(phase="run")
    view.cursor(1.0, 2.0, fps=60)
    view.add_trial({})
    view.set_blocks([])
    view.close()
    assert view.stop_requested is False


# ---------------------------------------------------------------- CLI wiring
def test_cli_defaults_to_the_web_panel() -> None:
    parser = build_parser()
    config = load_config(parser.parse_args([]))
    assert config.dashboard is True
    assert config.dashboard_port == 8765
    assert config.dashboard_open is True
    assert load_config(parser.parse_args(["--no-dashboard"])).dashboard is False
    assert load_config(parser.parse_args(["--no-open-dashboard"])).dashboard_open is False
    assert load_config(parser.parse_args(["--run-now"])).dashboard is True


def test_lsl_state_stream_lives_only_during_a_run(station) -> None:
    """Enabled while idle -> no outlet; the run opens it, its end closes it."""
    import time as _time

    import pylsl

    name = f"WebGridStateTest-{_time.time_ns()}"
    status, payload = _post(station, "/api/lsl", {"enabled": True, "stream": name, "rate": 20})
    assert status == 200
    assert payload["enabled"] is True and payload["live"] is False
    assert payload["stream"] == name
    # Nothing is published between sessions.
    assert pylsl.resolve_byprop("name", name, timeout=2) == []

    station._begin_run(ExperimentConfig(blocks=1, targets=2), "test")
    try:
        streams = pylsl.resolve_byprop("name", name, timeout=15)
        assert streams, "state stream was not opened with the run"
        inlet = pylsl.StreamInlet(streams[0])
        inlet.open_stream(timeout=5)
        try:
            sample, _ts = inlet.pull_sample(timeout=10)
            assert sample is not None
            doc = json.loads(sample[0])
            assert doc["schema"] == "webgrid.state/1"
            assert doc["status"] == "running"
            assert "blocks" in doc and "hits" in doc and "phase" in doc
        finally:
            inlet.close_stream()

        _, state = _get(station, "/api/state")
        assert state["lsl"]["enabled"] is True
        assert state["lsl"]["live"] is True
        assert state["lsl"]["sent"] > 0
    finally:
        station._end_run(station._current["id"], "finished")

    # After the run the outlet is gone, and no more samples are produced.
    assert pylsl.resolve_byprop("name", name, timeout=3) == []
    status = station.lsl_status()
    assert status["enabled"] is True and status["live"] is False

    status, payload = _post(station, "/api/lsl", {"enabled": False})
    assert status == 200 and payload["enabled"] is False


def test_lsl_state_rejects_bad_rate(station) -> None:
    status, payload = _post(station, "/api/lsl", {"enabled": True, "rate": 0.1})
    assert status == 400
    assert "频率" in payload["error"]


def test_lsl_snapshot_tracks_the_run(station) -> None:
    station._begin_run(ExperimentConfig(blocks=2, targets=3, rows=5, cols=5), "test")
    station._view_update(
        station._current["id"],
        phase="run",
        block=2,
        trials_done=2,
        subject="s9",
        session_id="abc",
        target={"index": 3, "row": 1, "col": 4, "label": "r2c5", "button": 1},
    )
    station._view_trial(station._current["id"], {"outcome": "hit", "misclicks": 2})
    station._view_trial(station._current["id"], {"outcome": "timeout", "misclicks": 0})
    doc = station.lsl_snapshot()
    assert doc["status"] == "running"
    assert doc["phase"] == "run"
    assert (doc["blocks"], doc["trials_per_block"], doc["block"], doc["trial"]) == (
        2,
        3,
        2,
        2,
    )
    assert doc["target"]["label"] == "r2c5"
    assert (doc["hits"], doc["timeouts"], doc["misclicks"]) == (1, 1, 2)
    assert doc["subject"] == "s9"
    station._end_run(station._current["id"], "aborted")
    assert station.lsl_snapshot()["status"] == "idle"


def test_lsl_state_defaults_come_from_config() -> None:
    config = ExperimentConfig(lsl_state_stream="MyState", lsl_state_rate=5.0)
    board = make_station(base_config=config, open_browser=False)
    try:
        assert board.lsl_status()["enabled"] is False
        status = board.start_lsl_state()
        assert status["stream"] == "MyState"
        assert status["rate"] == 5.0
    finally:
        board.close()


def test_lsl_state_closes_when_the_end_screen_appears(station) -> None:
    """The renderer publishes phase=done at the end screen; the stream must go
    away at that moment, not when the run teardown finishes."""
    name = "EndScreenTest"
    station.start_lsl_state(name, 20)
    station._begin_run(ExperimentConfig(blocks=1, targets=1), "test")
    run_id = station._current["id"]
    assert station.lsl_status()["live"] is True

    station._view_update(run_id, phase="run", trials_done=1)
    assert station.lsl_status()["live"] is True

    station._view_update(run_id, phase="done", target=None)
    status = station.lsl_status()
    assert status["live"] is False, "stream should close when the end screen shows"
    assert status["enabled"] is True, "but stay enabled for the next run"
    assert status["sent"] >= 1

    # The later teardown is harmless (the outlet is already gone).
    station._end_run(run_id, "finished")
    assert station.lsl_status()["live"] is False


def test_final_sample_is_marked(station) -> None:
    station._begin_run(ExperimentConfig(blocks=1, targets=1), "test")
    station._view_update(station._current["id"], phase="done")
    assert station.lsl_snapshot()["final"] is False
    assert station.lsl_snapshot(final=True)["final"] is True
    station._end_run(station._current["id"], "finished")


def test_sse_delivers_runs_and_trials(station) -> None:
    messages: list[dict] = []
    ready = threading.Event()

    def reader() -> None:
        with urllib.request.urlopen(_url(station, "/events"), timeout=5) as stream:
            for raw in stream:
                line = raw.decode("utf-8").strip()
                if line.startswith("data: "):
                    messages.append(json.loads(line[6:]))
                    if len(messages) >= 2:
                        ready.set()
                        return

    threading.Thread(target=reader, daemon=True).start()
    for _ in range(100):
        if messages:
            break
        time.sleep(0.02)
    station.request_start(ExperimentConfig(blocks=1, targets=1), "test")

    def fake_run(config, view):
        view.add_trial({"trial": 1, "outcome": "hit", "rt": 0.2, "misclicks": 0})
        return {"hits": 1, "attempts": 1, "bps": 0.0, "duration_s": 1.0}

    thread = threading.Thread(target=station.serve, args=(fake_run,), daemon=True)
    thread.start()
    assert ready.wait(8)
    # serve() keeps waiting for the next run by design; the thread is a daemon.

    assert messages[0]["reset"] is True
    assert any(m["trials"] for m in messages)
    assert all("schema" not in m for m in messages)  # form comes from /api/config
    assert messages[-1]["runs"] and messages[-1]["runs"][0]["hits"] == 1
