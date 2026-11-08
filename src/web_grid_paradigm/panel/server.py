"""HTTP plumbing for the control panel: routes, SSE stream and page asset."""

from __future__ import annotations

import json
import mimetypes
import socket
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import TYPE_CHECKING, Any

from loguru import logger

from ..config import ExperimentConfig

if TYPE_CHECKING:
    from .state import Station

class _Server(ThreadingHTTPServer):
    daemon_threads = True
    # http.server enables SO_REUSEADDR, which on Windows lets a second process
    # bind the same port and silently steal connections; an exclusive bind
    # makes a port clash fail loudly instead.
    allow_reuse_address = sys.platform != "win32"

    def server_bind(self) -> None:
        if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()



# ----------------------------------------------------------------------
# HTTP plumbing
# ----------------------------------------------------------------------
STATIC_PREFIX = "/assets/"


def _static_file(relative: str) -> bytes | None:
    """Read a file from the built Vue app (``panel/static``).

    Returns ``None`` for unknown paths and for anything trying to escape the
    bundle directory.
    """
    parts = [part for part in relative.split("/") if part not in ("", ".", "..")]
    if not parts:
        parts = ["index.html"]
    root = resources.files("web_grid_paradigm.panel").joinpath("static")
    candidate = root
    for part in parts:
        candidate = candidate.joinpath(part)
    if not candidate.is_file():
        return None
    return candidate.read_bytes()


def _content_type(name: str) -> str:
    guessed, _ = mimetypes.guess_type(name)
    if guessed is None:
        return "application/octet-stream"
    if guessed.startswith("text/") or guessed in (
        "application/javascript",
        "application/json",
    ):
        return f"{guessed}; charset=utf-8"
    return guessed


def _make_handler(station: Station) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "webgrid-station"

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            try:
                if path in ("/", "/index.html"):
                    self._send(
                        HTTPStatus.OK,
                        _static_file("index.html") or b"missing bundle",
                        "text/html; charset=utf-8",
                    )
                elif path.startswith(STATIC_PREFIX):
                    relative = path[len(STATIC_PREFIX) :]
                    body = _static_file(f"assets/{relative}")
                    if body is None:
                        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                    else:
                        self._send(HTTPStatus.OK, body, _content_type(relative))
                elif path in ("/app", "/app/"):
                    self.send_response(HTTPStatus.FOUND)
                    self.send_header("Location", "/")
                    self.end_headers()
                elif path == "/api/state":
                    self._json(HTTPStatus.OK, station.snapshot())
                elif path == "/api/config":
                    self._json(HTTPStatus.OK, station.config_payload())
                elif path == "/events":
                    self._events()
                else:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return  # browser tab closed

        def do_POST(self) -> None:
            path = self.path.split("?", 1)[0]
            try:
                if path == "/api/start":
                    payload = self._read_json()
                    self._json(HTTPStatus.OK, {"ok": True, "config": station.start(payload)})
                elif path == "/api/stop":
                    stopped = station.request_stop()
                    self._json(HTTPStatus.OK, {"ok": True, "stopping": stopped})
                elif path == "/api/lsl":
                    payload = self._read_json()
                    if payload.get("enabled", True):
                        status = station.start_lsl_state(
                            payload.get("stream"), payload.get("rate")
                        )
                    else:
                        status = station.stop_lsl_state()
                    self._json(HTTPStatus.OK, status)
                elif path == "/api/reward/test":
                    self._json(HTTPStatus.OK, station.reward_self_test(self._read_json()))
                elif path == "/api/reward/connect":
                    payload = self._read_json()
                    self._json(
                        HTTPStatus.OK,
                        station.connect_reward(
                            payload.get("port"), payload.get("baud")
                        ),
                    )
                elif path == "/api/reward/disconnect":
                    self._json(HTTPStatus.OK, station.disconnect_reward())
                else:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            except (TypeError, ValueError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except RuntimeError as exc:
                self._json(HTTPStatus.CONFLICT, {"error": str(exc)})

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw or b"{}")
            except json.JSONDecodeError as exc:
                raise ValueError(f"无效的 JSON: {exc}") from exc
            if not isinstance(payload, dict):
                raise TypeError("请求体必须是 JSON 对象")
            return payload

        def _events(self) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            def write(data: bytes) -> None:
                self.wfile.write(data)
                self.wfile.flush()

            station.stream(write)

        def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, default=str).encode()
            self._send(status, body, "application/json; charset=utf-8")

        def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            logger.trace("station http: " + format, *args)

    return Handler


def start_station(
    host: str,
    port: int,
    *,
    base_config: ExperimentConfig | None = None,
    control: bool = True,
    open_browser: bool = False,
) -> Station | None:
    """Start the panel; on failure log a warning and return ``None``."""
    from .state import Station, lan_ipv4_addresses

    try:
        station = Station(
            host,
            port,
            base_config=base_config,
            control=control,
            open_browser=open_browser,
        )
    except OSError as exc:
        logger.warning(
            "web panel not started on {}:{} ({}); the session can still run "
            "from the command line",
            host,
            port,
            exc,
        )
        return None
    station.attach_logs()
    logger.info("web control panel: {}", station.url)
    lan_urls = station.lan_urls
    for url in lan_urls:
        logger.info("  reachable from another computer: {}", url)
    if station.is_wildcard:
        logger.warning("the web panel is reachable from other computers")
        if not lan_urls:
            logger.warning(
                "no LAN IPv4 address was found; check the network connection"
            )
    elif station.is_loopback:
        addresses = lan_ipv4_addresses()
        if addresses:
            logger.info(
                "  only reachable on this computer; to open it from another one, "
                "add --dashboard-host 0.0.0.0 and use http://{}:{}/",
                addresses[0],
                station.port,
            )
        else:
            logger.info(
                "  only reachable on this computer; add --dashboard-host 0.0.0.0 "
                "to open it from another computer"
            )
    if base_config is not None and base_config.lsl_state:
        try:
            station.start_lsl_state()
        except Exception as exc:  # noqa: BLE001 - the panel still works
            logger.warning("could not start the LSL state stream: {}", exc)
    return station
