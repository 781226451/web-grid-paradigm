"""Read the Windows pointer directly, independently of Pyglet's event cache.

GetCursorPos, ScreenToClient and GetClientRect use the calling thread's DPI
coordinate space.  Mapping the resulting client coordinates to the layout
keeps mouse and drawing coordinates aligned even with Windows scaling.
No process-wide DPI setting or desktop pointer capture is needed.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Any

from ..core.geometry import Layout


def _load_user32() -> Any:
    api = ctypes.WinDLL("user32", use_last_error=True)
    signatures = {
        "GetCursorPos": [ctypes.POINTER(wintypes.POINT)],
        "GetClientRect": [wintypes.HWND, ctypes.POINTER(wintypes.RECT)],
        "ScreenToClient": [wintypes.HWND, ctypes.POINTER(wintypes.POINT)],
        "ClientToScreen": [wintypes.HWND, ctypes.POINTER(wintypes.POINT)],
        "SetCursorPos": [ctypes.c_int, ctypes.c_int],
    }
    for name, args in signatures.items():
        function = getattr(api, name)
        function.argtypes = args
        function.restype = wintypes.BOOL
    return api


class WindowsPointer:
    """Position-only adapter; PsychoPy still supplies the mouse button edges."""

    def __init__(self, hwnd: int, layout: Layout, *, api: Any = None) -> None:
        self.hwnd = hwnd
        self.layout = layout
        self._api = api if api is not None else _load_user32()
        self.client_size: tuple[int, int] | None = None

    def _call(self, name: str, *args: Any) -> None:
        if not getattr(self._api, name)(*args):
            code = getattr(ctypes, "get_last_error", lambda: 0)()
            raise OSError(f"Windows mouse {name} failed (winerror={code})")

    def _client_rect(self) -> wintypes.RECT:
        rect = wintypes.RECT()
        self._call("GetClientRect", self.hwnd, ctypes.byref(rect))
        width, height = rect.right - rect.left, rect.bottom - rect.top
        if width <= 0 or height <= 0:
            raise OSError("Windows mouse client area is empty")
        self.client_size = width, height
        return rect

    def getPos(self) -> tuple[float, float]:
        rect = self._client_rect()
        point = wintypes.POINT()
        self._call("GetCursorPos", ctypes.byref(point))
        self._call("ScreenToClient", self.hwnd, ctypes.byref(point))
        width, height = rect.right - rect.left, rect.bottom - rect.top
        return (
            ((point.x - rect.left) / width - 0.5) * self.layout.window_w,
            (0.5 - (point.y - rect.top) / height) * self.layout.window_h,
        )

    def setPos(self, position: tuple[float, float]) -> None:
        rect = self._client_rect()
        width, height = rect.right - rect.left, rect.bottom - rect.top
        point = wintypes.POINT(
            round(rect.left + (position[0] / self.layout.window_w + 0.5) * width),
            round(rect.top + (0.5 - position[1] / self.layout.window_h) * height),
        )
        self._call("ClientToScreen", self.hwnd, ctypes.byref(point))
        self._call("SetCursorPos", point.x, point.y)
