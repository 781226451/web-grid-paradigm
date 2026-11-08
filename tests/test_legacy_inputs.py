from __future__ import annotations

import json
import socket
import time

from web_grid_paradigm.legacy_inputs import AutoPilot, UdpCursorSource


def send(source: UdpCursorSource, payload: dict) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(json.dumps(payload).encode("utf-8"), ("127.0.0.1", source.port))


def poll_until(source: UdpCursorSource, deadline: float = 1.0):
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        state = source.poll(now=time.monotonic())
        if state is not None:
            return state
        time.sleep(0.005)
    return None


def test_udp_position_and_click_edges() -> None:
    with UdpCursorSource("127.0.0.1", 0) as source:
        send(source, {"x": 0.25, "y": -0.5, "click": 1})
        state = poll_until(source)
        assert state is not None
        assert (state.x, state.y) == (0.25, -0.5)
        assert state.clicks == (1,)

        send(source, {"x": 0.25, "y": -0.5, "click": 1})
        state = poll_until(source)
        assert (
            state is not None and state.clicks == ()
        )  # held button is not a new click

        send(source, {"x": 0.3, "y": -0.4, "click": 0})
        state = poll_until(source)
        assert state is not None and state.clicks == ()

        send(source, {"x": 0.3, "y": -0.4, "click": 1})
        state = poll_until(source)
        assert state is not None and state.clicks == (1,)


def test_udp_one_shot_event_and_clamping() -> None:
    with UdpCursorSource("127.0.0.1", 0) as source:
        send(source, {"x": 5.0, "y": -9.0, "event": "click", "button": 2})
        state = poll_until(source)
        assert state is not None
        assert (state.x, state.y) == (1.0, -1.0)
        assert state.clicks == (2,)

        send(source, {"x": 0.1, "y": 0.1, "select": True})
        state = poll_until(source)
        assert state is not None and state.clicks == (1,)


def test_udp_smoothing() -> None:
    with UdpCursorSource("127.0.0.1", 0, smoothing=0.5) as source:
        send(source, {"x": 1.0, "y": 1.0})
        first = poll_until(source)
        assert first is not None and (first.x, first.y) == (1.0, 1.0)

        send(source, {"x": -1.0, "y": -1.0})
        second = poll_until(source)
        assert second is not None
        assert second.x == 0.0 and second.y == 0.0


def test_udp_malformed_packets_are_ignored() -> None:
    with UdpCursorSource("127.0.0.1", 0) as source:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(b"not json", ("127.0.0.1", source.port))
            sock.sendto(b'{"x": "bad", "y": 0}', ("127.0.0.1", source.port))
        assert poll_until(source, deadline=0.2) is None
        assert source.invalid_packets == 2


def test_autopilot_reaches_target_and_clicks_once() -> None:
    pilot = AutoPilot(speed=5.0)
    target = (0.5, 0.5)
    clicks = []
    for _ in range(100):
        state = pilot.poll(0.05, target)
        clicks.extend(state.clicks)
        if state.x == target[0] and state.y == target[1]:
            break
    assert (pilot.x, pilot.y) == target
    assert clicks == [1]

    # Re-polling the same target must not repeat the click.
    assert pilot.poll(0.05, target).clicks == ()
    # A new target re-arms the click.
    state = pilot.poll(0.05, (0.0, 0.0))
    assert state.clicks == () or state.clicks == (1,)
