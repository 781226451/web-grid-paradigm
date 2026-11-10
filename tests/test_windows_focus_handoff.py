"""Windows foreground handoff used before the mouse is centred."""

from __future__ import annotations

import pytest

from web_grid_paradigm.velocity_inputs.windows_focus import WindowsFocus


class NativeFocus:
    def __init__(self):
        self.foreground = 100  # browser in another thread
        self.focus = 200  # local focus alone misleadingly belongs to Pyglet
        self.attached = False
        self.attach_allowed = True
        self.attachments = []
        self.raise_on_focus = False

    def GetForegroundWindow(self):
        return self.foreground

    def GetFocus(self):
        return self.focus

    def GetCapture(self):
        return 0

    def SetForegroundWindow(self, hwnd):
        if self.attached:
            self.foreground = hwnd
        return self.foreground == hwnd

    def SetFocus(self, hwnd):
        if self.raise_on_focus:
            raise OSError("focus failed")
        self.focus = hwnd

    def BringWindowToTop(self, hwnd):
        return True

    def GetWindowThreadProcessId(self, hwnd, process_id):
        return 10

    def AttachThreadInput(self, current, other, attach):
        self.attachments.append((current, other, attach))
        if not self.attach_allowed:
            return False
        self.attached = attach
        return True


def test_local_pyglet_focus_is_not_enough_when_browser_is_foreground():
    native = NativeFocus()
    focus = WindowsFocus(200, api=native, thread_id=20)
    assert focus.ready() is False
    assert focus.acquire() is True
    assert native.foreground == native.focus == 200
    assert native.attachments == [(20, 10, True), (20, 10, False)]
    assert native.attached is False


def test_already_focused_window_does_not_attach_other_threads():
    native = NativeFocus()
    native.foreground = 200
    focus = WindowsFocus(200, api=native, thread_id=20)
    assert focus.acquire() is True
    assert native.attachments == []


def test_failed_handoff_does_not_claim_that_input_is_ready():
    native = NativeFocus()
    native.attach_allowed = False
    focus = WindowsFocus(200, api=native, thread_id=20)
    assert focus.acquire() is False
    assert native.foreground == 100
    assert native.attached is False


def test_native_focus_error_always_detaches_input_queues():
    native = NativeFocus()
    native.raise_on_focus = True
    focus = WindowsFocus(200, api=native, thread_id=20)
    with pytest.raises(OSError, match="focus failed"):
        focus.acquire()
    assert native.attachments == [(20, 10, True), (20, 10, False)]
    assert native.attached is False
