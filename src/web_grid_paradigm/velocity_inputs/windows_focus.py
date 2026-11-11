"""Transfer input focus to a newly started experiment on Windows.

A browser can remain the foreground application after requesting a run over
HTTP, even if Pyglet reports local focus.  Request the foreground window and
keyboard focus together, and verify Windows' state before enabling input.
Thread input queues are attached only for the startup handoff, then detached.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Any


def _load_user32() -> Any:
    api = ctypes.WinDLL("user32", use_last_error=True)
    signatures = {
        "GetForegroundWindow": ([], wintypes.HWND),
        "GetFocus": ([], wintypes.HWND),
        "GetCapture": ([], wintypes.HWND),
        "SetForegroundWindow": ([wintypes.HWND], wintypes.BOOL),
        "SetFocus": ([wintypes.HWND], wintypes.HWND),
        "BringWindowToTop": ([wintypes.HWND], wintypes.BOOL),
        "GetWindowThreadProcessId": (
            [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD
        ),
        "AttachThreadInput": (
            [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL], wintypes.BOOL
        ),
    }
    for name, (args, result) in signatures.items():
        function = getattr(api, name)
        function.argtypes = args
        function.restype = result
    return api


class WindowsFocus:
    def __init__(
        self, hwnd: int, *, api: Any = None, thread_id: int | None = None
    ) -> None:
        self.hwnd = hwnd
        self._api = api if api is not None else _load_user32()
        if thread_id is None:
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.GetCurrentThreadId.argtypes = []
            kernel.GetCurrentThreadId.restype = wintypes.DWORD
            thread_id = kernel.GetCurrentThreadId()
        self._thread_id = thread_id

    def ready(self) -> bool:
        return (
            self._api.GetForegroundWindow() == self.hwnd
            and self._api.GetFocus() == self.hwnd
        )

    def acquire(self) -> bool:
        """One startup attempt; never synthesize a click or keyboard input."""
        if self.ready():
            return True
        if self._api.GetForegroundWindow() != self.hwnd:
            self._api.SetForegroundWindow(self.hwnd)
        if self._api.GetForegroundWindow() != self.hwnd:
            foreground = self._api.GetForegroundWindow()
            other_thread = (
                self._api.GetWindowThreadProcessId(foreground, None)
                if foreground else 0
            )
            attached = False
            try:
                if other_thread and other_thread != self._thread_id:
                    attached = bool(
                        self._api.AttachThreadInput(self._thread_id, other_thread, True)
                    )
                if attached:
                    self._api.BringWindowToTop(self.hwnd)
                    self._api.SetForegroundWindow(self.hwnd)
                    if self._api.GetForegroundWindow() == self.hwnd:
                        self._api.SetFocus(self.hwnd)
            finally:
                if attached:
                    self._api.AttachThreadInput(self._thread_id, other_thread, False)
        if self._api.GetForegroundWindow() == self.hwnd:
            # Pyglet handles WM_SETFOCUS on its top-level window, not its
            # drawing child.  Focusing the child would disable exclusive input.
            self._api.SetFocus(self.hwnd)
        return self.ready()

    def snapshot(self) -> dict[str, int | bool]:
        return {
            "foreground_hwnd": self._api.GetForegroundWindow() or 0,
            "focus_hwnd": self._api.GetFocus() or 0,
            "capture_hwnd": self._api.GetCapture() or 0,
            "window_hwnd": self.hwnd,
            "ready": self.ready(),
        }
