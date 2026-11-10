"""Mouse position polling with DPI scaling and stale window event coordinates."""

from __future__ import annotations

from ctypes import c_void_p
from types import SimpleNamespace

import pytest

from web_grid_paradigm.core.config import ExperimentConfig
from web_grid_paradigm.core.geometry import Layout
from web_grid_paradigm.velocity_inputs import DeviceContext, MouseVelocitySource
from web_grid_paradigm.velocity_inputs.mouse import _window_handle
from web_grid_paradigm.velocity_inputs.router import InputReader
from web_grid_paradigm.velocity_inputs.windows_pointer import WindowsPointer


LAYOUT = Layout.create(1440, 900, 12, 12)


def test_window_handle_unwraps_ctypes_hwnd() -> None:
    view = SimpleNamespace(_view_hwnd=c_void_p(42))
    assert _window_handle(SimpleNamespace(winHandle=view)) == 42


class FakeWindows:
    def __init__(self, size=(1440, 900), origin=(-1920, 100)):
        self.size = size
        self.origin = origin
        self.position = origin
        self.failed_call = None

    def GetClientRect(self, hwnd, rect):
        rect._obj.right, rect._obj.bottom = self.size
        return self.failed_call != "GetClientRect"

    def GetCursorPos(self, point):
        point._obj.x, point._obj.y = self.position
        return self.failed_call != "GetCursorPos"

    def ScreenToClient(self, hwnd, point):
        point._obj.x -= self.origin[0]
        point._obj.y -= self.origin[1]
        return self.failed_call != "ScreenToClient"

    def ClientToScreen(self, hwnd, point):
        point._obj.x += self.origin[0]
        point._obj.y += self.origin[1]
        return self.failed_call != "ClientToScreen"

    def SetCursorPos(self, x, y):
        self.position = x, y
        return self.failed_call != "SetCursorPos"


@pytest.mark.parametrize("size", [(1440, 900), (2160, 1350), (2880, 1800)])
def test_native_position_maps_client_area_to_layout(size):
    api = FakeWindows(size=size)
    pointer = WindowsPointer(42, LAYOUT, api=api)
    # Corners, centre and a point outside the client area on another monitor.
    for fraction, expected in [
        ((0.0, 0.0), (-720.0, 450.0)),
        ((1.0, 1.0), (720.0, -450.0)),
        ((0.5, 0.5), (0.0, 0.0)),
        ((1.5, -0.5), (1440.0, 900.0)),
    ]:
        api.position = tuple(
            round(origin + extent * part)
            for origin, extent, part in zip(api.origin, size, fraction)
        )
        assert pointer.getPos() == pytest.approx(expected)
    assert pointer.client_size == size


def test_center_uses_the_same_scaled_client_coordinates_as_reading():
    api = FakeWindows(size=(2880, 1800))
    pointer = WindowsPointer(42, LAYOUT, api=api)
    pointer.setPos((0.0, 0.0))
    assert api.position == (-480, 1000)
    assert pointer.getPos() == (0.0, 0.0)
    pointer.setPos((200.0, -150.0))
    assert pointer.getPos() == pytest.approx((200.0, -150.0))


@pytest.mark.parametrize("call", ["GetClientRect", "GetCursorPos", "ScreenToClient"])
def test_failed_native_read_cannot_turn_into_a_corner_position(call):
    api = FakeWindows()
    api.failed_call = call
    pointer = WindowsPointer(42, LAYOUT, api=api)
    with pytest.raises(OSError, match=call):
        pointer.getPos()


@pytest.mark.parametrize("call", ["ClientToScreen", "SetCursorPos"])
def test_failed_native_center_is_reported(call):
    api = FakeWindows()
    api.failed_call = call
    pointer = WindowsPointer(42, LAYOUT, api=api)
    with pytest.raises(OSError, match=call):
        pointer.setPos((0.0, 0.0))


def test_minimized_client_cannot_be_used_for_position_mapping():
    pointer = WindowsPointer(42, LAYOUT, api=FakeWindows(size=(0, 0)))
    with pytest.raises(OSError, match="empty"):
        pointer.getPos()


def test_windows_source_tracks_native_mouse_when_pyglet_cache_stops(monkeypatch):
    from psychopy import event
    from web_grid_paradigm.velocity_inputs import mouse as module

    class Focus:
        def acquire(self):
            return True

    api = FakeWindows(size=(2880, 1800))
    pointer = WindowsPointer(42, LAYOUT, api=api)
    cached_mouse = SimpleNamespace(
        getPos=lambda: (100.0, 50.0),
        getPressed=lambda: [False, False, False],
    )
    monkeypatch.setattr(event, "Mouse", lambda **kwargs: cached_mouse)
    monkeypatch.setattr(module, "WindowsFocus", lambda *args: Focus())
    monkeypatch.setattr(module, "WindowsPointer", lambda *args: pointer)
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="win32"))
    context = DeviceContext(layout=LAYOUT, window=SimpleNamespace(_hw_handle=42))
    source = MouseVelocitySource(context=context)
    reader = InputReader(context.window, LAYOUT, ExperimentConfig(), source=source)
    reader.center_cursor(0.0)
    assert reader.poll_cursor(1.0) == (0.0, 0.0)
    assert source.status().device["driver"] == "win32.GetCursorPos"

    # Large movement followed by immediate reversal, with no Pyglet position
    # updates.  The experiment cursor must follow the actual OS pointer.
    for now, position in enumerate([(700, -400), (-700, 400), (0, 0)], start=2):
        pointer.setPos(position)
        assert reader.poll_cursor(float(now)) == pytest.approx(position)
    reader.close()


def test_centring_acquires_focus_before_warping(monkeypatch):
    from web_grid_paradigm.velocity_inputs import mouse as module

    calls: list[object] = []

    class Focus:
        def acquire(self):
            calls.append("focus")
            return True

    class Pointer:
        def setPos(self, position):
            calls.append(("warp", position))

        def getPos(self):
            return (0.0, 0.0)

    class Device:
        def getPos(self):
            return (0.0, 0.0)

        def setPos(self, position):
            calls.append(("device", position))

        def getPressed(self):
            return [False, False, False]

    monkeypatch.setattr(module, "WindowsFocus", lambda *args: Focus())
    monkeypatch.setattr(module, "WindowsPointer", lambda *args: Pointer())
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="win32"))
    context = DeviceContext(layout=LAYOUT, window=SimpleNamespace(_hw_handle=42))
    source = MouseVelocitySource(context=context, device=Device())
    source.open()

    assert source.center_pointer() is True
    assert calls[0] == "focus"
    assert calls[1] == ("warp", (0.0, 0.0))


def test_centring_reports_a_failed_foreground_handoff(monkeypatch):
    from web_grid_paradigm.velocity_inputs import mouse as module

    class Focus:
        def acquire(self):
            return False

    class Pointer:
        def setPos(self, position):
            raise AssertionError("must not warp without focus")

    monkeypatch.setattr(module, "WindowsFocus", lambda *args: Focus())
    monkeypatch.setattr(module, "WindowsPointer", lambda *args: Pointer())
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="win32"))
    context = DeviceContext(layout=LAYOUT, window=SimpleNamespace(_hw_handle=42))
    source = MouseVelocitySource(context=context, device=SimpleNamespace())
    source.open()

    assert source.center_pointer() is False
    assert "foreground" in (source.status().error or "")


def test_native_pointer_is_retried_after_the_window_is_shown(monkeypatch):
    from web_grid_paradigm.velocity_inputs import mouse as module

    created: list[object] = []

    class Focus:
        def acquire(self):
            return True

    class Pointer:
        def setPos(self, position):
            pass

        def getPos(self):
            return (0.0, 0.0)

    def make_pointer(*args):
        created.append(args)
        if len(created) == 1:
            raise OSError("window not ready")
        return Pointer()

    monkeypatch.setattr(module, "WindowsFocus", lambda *args: Focus())
    monkeypatch.setattr(module, "WindowsPointer", make_pointer)
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="win32"))
    context = DeviceContext(layout=LAYOUT, window=SimpleNamespace(_hw_handle=42))
    source = MouseVelocitySource(context=context, device=SimpleNamespace())

    source.open()
    assert source._pointer is None
    assert source.center_pointer() is True
    assert isinstance(source._pointer, Pointer)


def test_native_pointer_skips_a_handle_with_no_usable_client(monkeypatch):
    from web_grid_paradigm.velocity_inputs import mouse as module

    tried: list[int] = []

    class Focus:
        def acquire(self):
            return True

    class BadPointer:
        def getPos(self):
            raise OSError("empty client area")

    class GoodPointer:
        def getPos(self):
            return (0.0, 0.0)

        def setPos(self, position):
            pass

    def make_pointer(hwnd, layout):
        tried.append(hwnd)
        return BadPointer() if hwnd == 42 else GoodPointer()

    monkeypatch.setattr(module, "WindowsFocus", lambda *args: Focus())
    monkeypatch.setattr(module, "WindowsPointer", make_pointer)
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="win32"))
    window = SimpleNamespace(winHandle=SimpleNamespace(_view_hwnd=42, _hwnd=43))
    source = MouseVelocitySource(
        context=DeviceContext(layout=LAYOUT, window=window),
        device=SimpleNamespace(),
    )

    source.open()
    assert tried == [42, 43]
    assert isinstance(source._pointer, GoodPointer)
