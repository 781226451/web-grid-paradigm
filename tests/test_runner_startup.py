"""Startup must wait for a displayed window and confirmed mouse centering."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from web_grid_paradigm.app import runner
from web_grid_paradigm.core.config import ExperimentConfig
from web_grid_paradigm.core.geometry import Layout
from web_grid_paradigm.velocity_inputs import DeviceContext, MouseVelocitySource
from web_grid_paradigm.velocity_inputs.router import InputReader


def make_startup(monkeypatch, *, ready_after=1, countdown=0.3):
    clock = SimpleNamespace(now=0.0, flips=0)
    rendered = []
    started = []

    class Mouse:
        pos = (-622.0, -200.0)  # WebUI start button from the reported session
        attempts = 0

        def setPos(self, position):
            self.attempts += 1
            if clock.flips < ready_after:
                raise OSError("window is not ready")
            self.pos = position

        def getPos(self):
            return self.pos

        def getPressed(self):
            return [False, False, False]

    def flip():
        clock.flips += 1
        clock.now += 0.1
        return clock.now

    app = object.__new__(runner.WebGridApp)
    app.cfg = ExperimentConfig(countdown_seconds=countdown)
    layout = Layout.create(1440, 900, 12, 12)
    device = Mouse()
    source = MouseVelocitySource(context=DeviceContext(layout=layout), device=device)
    app.input = InputReader(None, layout, app.cfg, source=source)
    app.win = SimpleNamespace(flip=flip)
    app.renderer = SimpleNamespace(
        draw_countdown=lambda now, pos: rendered.append((clock.flips, pos)),
    )
    app.reporter = Mock()
    app.monitor = SimpleNamespace(stop_requested=False)
    app.block = 1
    app._cursor_centered = False
    app._centering_started = 0.0
    app._exit = False
    app.countdown_start = 0.0
    app._publish = lambda *args: None

    def begin_run(now):
        started.append((now, app.input.cursor_px))
        app.state = "run"

    app._begin_run = begin_run
    app._run_frame = lambda now: setattr(app, "_exit", True)
    monkeypatch.setattr(runner.core, "getTime", lambda: clock.now)
    monkeypatch.setattr(runner.event, "getKeys", lambda: [])
    app._begin_countdown(clock.now)
    return app, device, clock, rendered, started


@pytest.mark.parametrize("countdown", [0.0, 0.3])
@pytest.mark.parametrize("ready_after", [1, 3])
def test_startup_shows_centre_and_retries_before_starting_task(
    monkeypatch, countdown, ready_after
):
    app, device, clock, rendered, started = make_startup(
        monkeypatch, ready_after=ready_after, countdown=countdown
    )
    assert device.attempts == 0  # constructor must not warp an unshown window
    app._loop()
    assert rendered and all(pos == (0.0, 0.0) for _, pos in rendered)
    assert device.pos == (0.0, 0.0)
    assert device.attempts == ready_after
    assert app._cursor_centered is True
    assert app.countdown_start == pytest.approx(ready_after * 0.1)
    assert started[0][0] >= app.countdown_start + countdown
    assert started[0][1] == (0.0, 0.0)
    app.reporter.countdown_start.assert_called_once_with(app.countdown_start)


def test_next_block_preserves_position_without_recentring(monkeypatch):
    app, device, clock, rendered, started = make_startup(monkeypatch, countdown=0.0)
    app._loop()
    attempts = device.attempts
    device.pos = (200.0, 150.0)
    app.input.poll_cursor(clock.now)
    app.block = 2
    app._begin_countdown(clock.now)
    assert device.attempts == attempts
    assert started[-1][1] == (200.0, 150.0)


def test_startup_failure_cannot_silently_begin_trials(monkeypatch):
    app, device, clock, rendered, started = make_startup(
        monkeypatch, ready_after=10_000, countdown=0.0
    )
    with pytest.raises(RuntimeError, match="centre"):
        app._loop()
    assert started == []
    assert clock.now < 11.0
    app.reporter.countdown_start.assert_not_called()


def test_escape_still_works_while_waiting_for_center(monkeypatch):
    app, device, clock, rendered, started = make_startup(monkeypatch, ready_after=10_000)
    monkeypatch.setattr(runner.event, "getKeys", lambda: ["escape"] if clock.flips else [])
    app._handle_stop = Mock()
    app._loop()
    app._handle_stop.assert_called_once()
    assert started == []


def test_start_page_is_always_shown_before_countdown(monkeypatch):
    app = object.__new__(runner.WebGridApp)
    app.cfg = SimpleNamespace()
    app.state = "intro"
    app.monitor = SimpleNamespace(stop_requested=False)
    app._publish = lambda *args: None
    app._last_frame = 0.0
    app._exit = False

    calls: list[str] = []

    class Renderer:
        def draw_intro(self):
            calls.append("draw_intro")

    class Input:
        cursor_px = (0.0, 0.0)

        def __init__(self):
            self.calls = 0

        def start_requested(self, now, keys):
            self.calls += 1
            return self.calls > 1

    app.renderer = Renderer()
    app.input = Input()
    app.win = SimpleNamespace(flip=lambda: 0.0)
    app._begin_countdown = lambda now: setattr(app, "_exit", True)
    monkeypatch.setattr(runner.event, "getKeys", lambda: [])
    monkeypatch.setattr(runner.core, "getTime", lambda: 0.0)

    app._loop()

    assert calls == ["draw_intro"]
