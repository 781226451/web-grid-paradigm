"""Web control panel: enter parameters, start a session, watch it live.

One process, one URL.  The HTTP server runs in a daemon thread; the main
thread waits for a start request, runs the PsychoPy session, and then waits
again, so the page can start another session without restarting anything.

Endpoints:

======  ==================================================================
GET     ``/``            the page (parameter form + live monitoring)
GET     ``/events``      Server-Sent Events stream (live updates)
GET     ``/api/state``   full JSON snapshot (scripts, debugging)
GET     ``/api/config``  form schema, defaults and the last used values
POST    ``/api/start``   validate the submitted parameters and start a run
POST    ``/api/stop``    abort the running session (same as pressing Esc)
======  ==================================================================

The render loop only ever touches in-memory state (lock + dict assignment);
serialisation and socket writes happen in the server threads, so monitoring
never disturbs stimulus timing.
"""

from __future__ import annotations

import json
import socket
import sys
import threading
import time
import webbrowser
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Any

from loguru import logger

from .config import ExperimentConfig

# ----------------------------------------------------------------------
# Parameter form (single source of truth for the page and for validation)
# ----------------------------------------------------------------------
_FORM: list[dict[str, Any]] = [
    # session
    {"name": "subject", "label": "被试", "type": "text", "group": "会话"},
    {"name": "session", "label": "会话标签", "type": "text", "group": "会话",
     "hint": "留空 = 当前时间戳"},
    {"name": "output_dir", "label": "数据目录", "type": "text", "group": "会话"},
    # design
    {"name": "blocks", "label": "Block 数", "type": "int", "min": 1, "max": 100,
     "group": "实验设计"},
    {"name": "targets", "label": "每个 Block 的 Trial 数", "type": "int",
     "min": 1, "max": 10000, "group": "实验设计"},
    {"name": "rows", "label": "Grid 行数", "type": "int", "min": 2, "max": 40,
     "group": "实验设计"},
    {"name": "cols", "label": "Grid 列数", "type": "int", "min": 2, "max": 40,
     "group": "实验设计"},
    {"name": "iti", "label": "Trial 间休息 (s)", "type": "float", "min": 0,
     "max": 60, "step": 0.5, "group": "实验设计", "hint": "0 = 无"},
    {"name": "block_rest", "label": "Block 间休息 (s)", "type": "float",
     "min": 0, "max": 600, "step": 5, "group": "实验设计"},
    # task
    {"name": "selection", "label": "选择方式", "type": "choice",
     "options": ["click", "dwell"], "group": "任务"},
    {"name": "dwell_time", "label": "停留时长 (s)", "type": "float", "min": 0.1,
     "max": 10, "step": 0.1, "group": "任务", "hint": "仅 dwell 模式"},
    {"name": "click_types", "label": "点击类型数", "type": "int", "min": 1,
     "max": 3, "group": "任务"},
    {"name": "feedback", "label": "反馈时长 (s)", "type": "float", "min": 0,
     "max": 5, "step": 0.05, "group": "任务"},
    {"name": "trial_timeout", "label": "单 Trial 超时 (s)", "type": "float",
     "min": 0, "max": 600, "step": 1, "group": "任务", "hint": "0 = 关闭"},
    {"name": "max_seconds", "label": "单 Block 时间上限 (s)", "type": "float",
     "min": 0, "max": 36000, "step": 30, "group": "任务", "hint": "0 = 关闭"},
    {"name": "countdown_seconds", "label": "倒计时 (s)", "type": "float",
     "min": 0, "max": 10, "step": 0.5, "group": "任务"},
    {"name": "seed", "label": "随机种子", "type": "int", "min": 0,
     "max": 2147483647, "group": "任务"},
    # input
    {"name": "input", "label": "输入方式", "type": "choice",
     "options": ["mouse", "keyboard", "udp", "demo"], "group": "输入"},
    {"name": "udp_host", "label": "UDP 地址", "type": "text", "group": "输入"},
    {"name": "udp_port", "label": "UDP 端口", "type": "int", "min": 1,
     "max": 65535, "group": "输入"},
    {"name": "smoothing", "label": "平滑 (0–0.95)", "type": "float", "min": 0,
     "max": 0.95, "step": 0.05, "group": "输入"},
    # display
    {"name": "fullscreen", "label": "全屏运行", "type": "bool", "group": "显示"},
    {"name": "window_width", "label": "窗口宽", "type": "int", "min": 640,
     "max": 7680, "group": "显示"},
    {"name": "window_height", "label": "窗口高", "type": "int", "min": 480,
     "max": 4320, "group": "显示"},
    {"name": "skip_instructions", "label": "跳过指导语", "type": "bool",
     "group": "显示"},
    {"name": "auto_exit", "label": "结束后自动关闭", "type": "bool", "group": "显示"},
    # markers / LSL
    {"name": "lsl", "label": "发布 LSL 标记", "type": "bool", "group": "标记"},
    {"name": "lsl_stream", "label": "标记流名称", "type": "text", "group": "标记"},
    {"name": "marker_udp", "label": "UDP 标记 (host:port)", "type": "text",
     "group": "标记"},
]
_FORM_BY_NAME = {field["name"]: field for field in _FORM}
_FORM_GROUPS = ["会话", "实验设计", "任务", "输入", "显示", "标记"]


def form_schema() -> list[dict[str, Any]]:
    """Field descriptions, in display order, with their group."""
    return [dict(field) for field in _FORM]


def coerce_params(payload: dict[str, Any], base: ExperimentConfig) -> ExperimentConfig:
    """Build a validated config from form values layered over ``base``."""
    unknown = sorted(set(payload) - set(_FORM_BY_NAME))
    if unknown:
        raise ValueError(f"未知参数: {', '.join(unknown)}")
    values: dict[str, Any] = {}
    for name, raw in payload.items():
        field = _FORM_BY_NAME[name]
        kind = field["type"]
        try:
            if kind == "bool":
                values[name] = bool(raw)
            elif kind == "int":
                values[name] = int(raw)
            elif kind == "float":
                values[name] = float(raw)
            elif kind == "choice":
                text = str(raw)
                if text not in field["options"]:
                    raise ValueError(f"{field['label']} 必须是 {field['options']}")
                values[name] = text
            else:
                values[name] = str(raw).strip()
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field['label']}: {exc}") from exc
    config = ExperimentConfig(**{**base.to_dict(), **values})
    config.validate()
    return config


class NullView:
    """Monitoring sink used when no web panel is attached."""

    stop_requested = False

    def update(self, **fields: Any) -> None:
        return None

    def cursor(self, x_px: float, y_px: float, fps: float | None = None) -> None:
        return None

    def add_trial(self, row: dict[str, Any]) -> None:
        return None

    def set_blocks(self, blocks: list[dict[str, Any]]) -> None:
        return None

    def close(self) -> None:
        return None


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


class Station:
    """Control panel server plus the shared state it publishes."""

    PUSH_INTERVAL = 0.1  # max ~10 SSE messages per second per browser
    KEEPALIVE = 15.0

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        *,
        base_config: ExperimentConfig | None = None,
        control: bool = True,
        open_browser: bool = False,
    ) -> None:
        self.base_config = base_config or ExperimentConfig()
        self.control = control
        self._cond = threading.Condition()
        self._version = 0
        self._closed = False
        self._status = "idle"  # idle | running | stopping
        self._session: dict[str, Any] = {}
        self._trials: list[dict[str, Any]] = []
        self._blocks: list[dict[str, Any]] = []
        self._logs: deque[tuple[int, str]] = deque(maxlen=400)
        self._log_seq = 0
        self._pending: list[tuple[ExperimentConfig, str]] = []
        self._stop = threading.Event()
        self._current: dict[str, Any] | None = None
        self._runs: list[dict[str, Any]] = []
        self._run_counter = 0
        self._sink_id: int | None = None
        self._last_params: dict[str, Any] = {}
        self._lsl_publisher: LslStatePublisher | None = None
        self._lsl_armed = False
        self._lsl_name = (base_config or ExperimentConfig()).lsl_state_stream
        self._lsl_rate = (base_config or ExperimentConfig()).lsl_state_rate
        self._lsl_sent = 0
        self._lsl_error: str | None = None
        self._lsl_counts = {"hits": 0, "timeouts": 0, "misclicks": 0}

        self._server = _Server((host, port), _make_handler(self))
        self.host = host
        self.port = int(self._server.server_address[1])
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="webgrid-station", daemon=True
        )
        self._thread.start()
        if open_browser:
            webbrowser.open(self.url)

    # ------------------------------------------------------------------
    @property
    def url(self) -> str:
        host = self.host
        if host in ("0.0.0.0", "", "::"):
            host = socket.gethostname()
        return f"http://{host}:{self.port}/"

    def attach_logs(self, level: str = "INFO") -> None:
        """Mirror loguru output into the page's log panel."""
        if self._sink_id is None:
            self._sink_id = logger.add(
                lambda message: self.log(str(message).rstrip("\n")),
                level=level,
                format="{time:HH:mm:ss} | {level: <7} | {message}",
                colorize=False,
            )

    def log(self, line: str) -> None:
        with self._cond:
            self._log_seq += 1
            self._logs.append((self._log_seq, line))
            self._bump()

    # --- control (called from HTTP threads) -------------------------------
    def request_start(self, config: ExperimentConfig, source: str = "web") -> None:
        with self._cond:
            if self._status != "idle":
                raise RuntimeError("已有实验在运行，请先中止或等待结束")
            self._pending.append((config, source))
            self._cond.notify_all()

    def request_stop(self) -> bool:
        with self._cond:
            if self._status != "running":
                return False
            self._status = "stopping"
            self._stop.set()
            self._bump()
        logger.warning("stop requested from the web panel")
        return True

    def run_config(self) -> dict[str, Any]:
        """Form defaults: base config, last used values, schema, extra info."""
        with self._cond:
            values = self._last_params or self._base_values()
            busy = self._status != "idle"
        return {
            "schema": form_schema(),
            "groups": _FORM_GROUPS,
            "values": values,
            "busy": busy,
            "control": self.control,
            "base_config": self.base_config.to_dict(),
        }

    def _base_values(self) -> dict[str, Any]:
        data = self.base_config.to_dict()
        data["output_dir"] = str(self.base_config.output_dir)
        return {name: data[name] for name in _FORM_BY_NAME}

    # --- LSL state stream (start/stop from the page) ----------------------
    def start_lsl_state(
        self, stream_name: str | None = None, rate: float | None = None
    ) -> dict[str, Any]:
        """Enable the state stream.

        The outlet only exists while a session runs: it is opened when a run
        starts and closed (after one final sample) when the run ends, so no
        traffic is produced between sessions.
        """
        name = (stream_name or self._lsl_name or self.base_config.lsl_state_stream)
        name = name.strip()
        hz = float(rate if rate is not None else self._lsl_rate)
        if not name:
            raise ValueError("LSL 状态流名称不能为空")
        if not 0.5 <= hz <= 100:
            raise ValueError("推送频率必须在 0.5–100 Hz 之间")
        with self._cond:
            self._lsl_armed = True
            self._lsl_name = name
            self._lsl_rate = hz
            running = self._status == "running"
            self._bump()
        if running:
            self._open_lsl_state()
        logger.info(
            "LSL state stream enabled ({}, {} Hz); it opens with each run", name, hz
        )
        return self.lsl_status()

    def stop_lsl_state(self) -> dict[str, Any]:
        with self._cond:
            self._lsl_armed = False
            self._bump()
        self._close_lsl_state()
        return self.lsl_status()

    def _open_lsl_state(self) -> None:
        """Create the outlet (called when a session starts)."""
        with self._cond:
            if not self._lsl_armed or self._lsl_publisher is not None:
                return
            name, hz = self._lsl_name, self._lsl_rate
        try:
            publisher = LslStatePublisher(self, name, hz)
            publisher.start()
        except Exception as exc:  # noqa: BLE001 - the session must still run
            logger.error("could not open the LSL state stream: {}", exc)
            with self._cond:
                self._lsl_error = f"{type(exc).__name__}: {exc}"
                self._bump()
            return
        with self._cond:
            self._lsl_publisher = publisher
            self._lsl_sent += publisher.sent
            self._bump()
        logger.info(
            "LSL state stream {!r} opened for this run; it closes when the run ends",
            name,
        )

    def _close_lsl_state(self, *, final_sample: bool = False) -> None:
        """Close the outlet, optionally publishing one last snapshot first."""
        with self._cond:
            publisher = self._lsl_publisher
            self._lsl_publisher = None
        if publisher is None:
            return
        publisher.stop(final_sample=final_sample)
        with self._cond:
            self._lsl_sent += publisher.sent
            self._bump()
        logger.info("LSL state stream {!r} closed", publisher.stream_name)

    def lsl_status(self) -> dict[str, Any]:
        with self._cond:
            publisher = self._lsl_publisher
            status = {
                "enabled": self._lsl_armed,
                "live": publisher is not None,
                "stream": self._lsl_name,
                "rate": self._lsl_rate,
                "sent": self._lsl_sent + (publisher.sent if publisher else 0),
                "consumers": publisher.outlet.consumers() if publisher else 0,
                "error": self._lsl_error or (publisher.error if publisher else None),
            }
        return status

    def lsl_snapshot(self, *, final: bool = False) -> dict[str, Any]:
        """The JSON document published on the LSL state stream.

        ``final=True`` marks the last sample, pushed when the end screen
        appears and the stream is about to be closed.
        """
        with self._cond:
            session = dict(self._session)
            config = session.get("config") or {}
            target = session.get("target") or None
            return {
                "schema": "webgrid.state/1",
                "utc": datetime.now(UTC).isoformat(timespec="milliseconds"),
                "status": self._status,  # idle | running | stopping
                "phase": session.get("phase"),
                "subject": session.get("subject"),
                "session_id": session.get("session_id"),
                "error": session.get("error"),
                "blocks": config.get("blocks"),
                "trials_per_block": config.get("targets"),
                "block": session.get("block"),
                "trial": session.get("trials_done"),
                "target": (
                    {
                        "index": target.get("index"),
                        "row": target.get("row"),
                        "col": target.get("col"),
                        "label": target.get("label"),
                        "button": target.get("button"),
                    }
                    if target
                    else None
                ),
                "dwell_progress": session.get("dwell_progress"),
                "elapsed_s": session.get("block_elapsed"),
                "fps": session.get("fps"),
                "hits": self._lsl_counts["hits"],
                "timeouts": self._lsl_counts["timeouts"],
                "misclicks": self._lsl_counts["misclicks"],
                "last_trial": self._trials[-1] if self._trials else None,
                "event_markers": bool(config.get("lsl")),
                "final": bool(final),
            }

    # --- producer (render loop, via SessionView) -------------------------
    def _view_update(self, run_id: int, **fields: Any) -> None:
        with self._cond:
            if not self._owns(run_id):
                return
            changed = False
            for key, value in fields.items():
                if self._session.get(key) != value:
                    self._session[key] = value
                    changed = True
            if changed:
                self._bump()
            # The end screen has appeared: stop the LSL state stream right
            # here (outside the lock) instead of waiting for the teardown.
            finished = (
                fields.get("phase") == "done" and self._lsl_publisher is not None
            )
        if finished:
            self._close_lsl_state(final_sample=True)

    def _view_cursor(
        self, run_id: int, x_px: float, y_px: float, fps: float | None
    ) -> None:
        with self._cond:
            if not self._owns(run_id):
                return
            self._session["cursor"] = (round(x_px, 1), round(y_px, 1))
            if fps is not None:
                self._session["fps"] = round(fps, 1)
            self._bump()

    def _view_trial(self, run_id: int, row: dict[str, Any]) -> None:
        with self._cond:
            if not self._owns(run_id):
                return
            self._trials.append(row)
            if row.get("outcome") == "hit":
                self._lsl_counts["hits"] += 1
            else:
                self._lsl_counts["timeouts"] += 1
            self._lsl_counts["misclicks"] += int(row.get("misclicks") or 0)
            self._bump()

    def _view_blocks(self, run_id: int, blocks: list[dict[str, Any]]) -> None:
        with self._cond:
            if not self._owns(run_id):
                return
            self._blocks = list(blocks)
            self._bump()

    def _owns(self, run_id: int) -> bool:
        return self._current is not None and self._current["id"] == run_id

    def _bump(self) -> None:
        self._version += 1
        self._cond.notify_all()

    # --- run loop (main thread) ------------------------------------------
    def serve(self, run: Callable[[ExperimentConfig, SessionView], Any]) -> None:
        """Run sessions one after another until the station is closed."""
        while True:
            request = self._next_request()
            if request is None:
                return
            config, source = request
            run_id = self._begin_run(config, source)
            view = SessionView(self, run_id)
            try:
                result = run(config, view)
            except KeyboardInterrupt:
                self._end_run(run_id, "stopped")
                raise
            except BaseException as exc:
                logger.exception("session failed: {}", exc)
                self._end_run(run_id, "failed", error=f"{type(exc).__name__}: {exc}")
                if isinstance(exc, SystemExit):
                    raise
            else:
                stopped = self._stop.is_set() or bool((result or {}).get("aborted"))
                self._end_run(run_id, "aborted" if stopped else "finished",
                              summary=result)

    def _next_request(self) -> tuple[ExperimentConfig, str] | None:
        with self._cond:
            while not self._pending and not self._closed:
                self._cond.wait(0.5)
            if self._closed:
                return None
            return self._pending.pop(0)

    def _begin_run(self, config: ExperimentConfig, source: str) -> int:
        with self._cond:
            self._run_counter += 1
            run_id = self._run_counter
            self._trials = []
            self._blocks = []
            self._lsl_counts = {"hits": 0, "timeouts": 0, "misclicks": 0}
            self._session = {
                "phase": "starting",
                "block": 1,
                "trials_done": 0,
                "config": config.to_dict(),
            }
            self._current = {
                "id": run_id,
                "source": source,
                "config": config,
                "started": time.time(),
            }
            self._status = "running"
            self._stop.clear()
            self._last_params = {
                name: getattr(config, name) for name in _FORM_BY_NAME
            }
            self._last_params["output_dir"] = str(config.output_dir)
            self._bump()
        logger.info(
            "run #{} started from the web panel ({}): {} block(s) x {} trials, "
            "{}x{} grid",
            run_id,
            source,
            config.blocks,
            config.targets,
            config.rows,
            config.cols,
        )
        self._open_lsl_state()
        return run_id

    def _end_run(
        self,
        run_id: int,
        status: str,
        *,
        summary: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        with self._cond:
            if self._current is None or self._current["id"] != run_id:
                return
            config = self._current["config"]
            record = {
                "id": run_id,
                "status": status,
                "subject": config.subject,
                "session_id": self._session.get("session_id", ""),
                "blocks": config.blocks,
                "trials_per_block": config.targets,
                "rows": config.rows,
                "cols": config.cols,
                "data_dir": self._session.get("data_dir", ""),
                "started": self._current["started"],
                "finished": time.time(),
                "error": error,
            }
            for key in ("attempts", "hits", "misclicks", "timeouts",
                        "bps", "duration_s"):
                record[key] = (summary or {}).get(key)
            self._runs.append(record)
            self._runs = self._runs[-50:]
            self._session["phase"] = "done"
            self._session["aborted"] = status != "finished"
            self._session["run_status"] = status
            self._session["error"] = error
            self._session["target"] = None
            self._current = None
            self._status = "idle"
            self._stop.clear()
            self._bump()
        logger.info("run #{} {}", run_id, status)
        # The state stream lives only as long as the run: publish one final
        # snapshot, then close the outlet so clients see the stream end.
        self._close_lsl_state(final_sample=True)

    # --- consumers (HTTP threads) ----------------------------------------
    def snapshot(self) -> dict[str, Any]:
        with self._cond:
            return self._payload(0, 0, reset=True)

    def config_payload(self) -> dict[str, Any]:
        return self.run_config()

    def _payload(
        self, trials_sent: int, log_seq: int, *, reset: bool
    ) -> dict[str, Any]:
        """Build one message; caller holds the lock."""
        return {
            "reset": reset,
            "server_time": time.time(),
            "status": self._status,
            "control": self.control,
            "state": dict(self._session),
            "trial_offset": trials_sent,
            "trials": self._trials[trials_sent:],
            "blocks": list(self._blocks),
            "runs": list(self._runs),
            "lsl": self.lsl_status(),
            "logs": [line for seq, line in self._logs if seq > log_seq],
        }

    def stream(self, write: Callable[[bytes], None]) -> None:
        """Feed one SSE client until the station closes or it disconnects."""
        version = -1
        trials_sent = 0
        log_seq = 0
        first = True
        while True:
            with self._cond:
                seen = version
                self._cond.wait_for(
                    lambda seen=seen: self._version != seen or self._closed,
                    timeout=self.KEEPALIVE,
                )
                if self._closed:
                    return
                payload = None
                if self._version != version:
                    version = self._version
                    payload = self._payload(trials_sent, log_seq, reset=first)
                    trials_sent = len(self._trials)
                    log_seq = self._log_seq
                    first = False
            if payload is None:
                write(b": keepalive\n\n")
            else:
                body = json.dumps(payload, ensure_ascii=False, default=str)
                write(f"data: {body}\n\n".encode())
            time.sleep(self.PUSH_INTERVAL)

    def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate form values and queue a run (HTTP thread)."""
        if not self.control:
            raise RuntimeError("此页面为只读监控")
        config = coerce_params(payload, self.base_config)
        self.request_start(config, source="web")
        return config.to_dict()

    # ------------------------------------------------------------------
    def close(self) -> None:
        with self._cond:
            if self._closed:
                return
            self._closed = True
            self._cond.notify_all()
        self.stop_lsl_state()
        if self._sink_id is not None:
            try:
                logger.remove(self._sink_id)
            except ValueError:
                pass
            self._sink_id = None
        self._server.shutdown()
        self._server.server_close()


class LslStatePublisher:
    """Background thread that pushes :meth:`Station.lsl_snapshot` over LSL."""

    def __init__(self, station: Station, stream_name: str, rate: float) -> None:
        from .markers import LslStateOutlet

        self.station = station
        self.stream_name = stream_name
        self.rate = float(rate)
        self.outlet = LslStateOutlet(stream_name)
        self.sent = 0
        self.error: str | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._loop, name="webgrid-lsl-state", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def push_once(self, *, final: bool = False) -> None:
        self.outlet.push(self.station.lsl_snapshot(final=final))
        self.sent = self.outlet.sent

    def _loop(self) -> None:
        period = 1.0 / self.rate
        while not self._stop.wait(period):
            try:
                self.push_once()
                self.error = None
            except Exception as exc:  # noqa: BLE001 - keep publishing
                self.error = f"{type(exc).__name__}: {exc}"
                logger.warning("LSL state push failed: {}", exc)
                time.sleep(1.0)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "live": True,
            "stream": self.stream_name,
            "rate": self.rate,
            "sent": self.sent,
            "consumers": self.outlet.consumers(),
            "error": self.error,
        }

    def stop(self, *, final_sample: bool = False) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if final_sample:
            try:
                self.push_once(final=True)
            except Exception as exc:  # noqa: BLE001 - closing anyway
                logger.debug("final LSL state push failed: {}", exc)
        try:
            self.outlet.close()
        except Exception as exc:  # noqa: BLE001 - teardown must not fail
            logger.debug("could not close the LSL state outlet: {}", exc)


class SessionView:
    """Per-run monitoring handle handed to the renderer."""

    def __init__(self, station: Station, run_id: int) -> None:
        self._station = station
        self._run_id = run_id

    @property
    def stop_requested(self) -> bool:
        return self._station._stop.is_set()

    def update(self, **fields: Any) -> None:
        self._station._view_update(self._run_id, **fields)

    def cursor(self, x_px: float, y_px: float, fps: float | None = None) -> None:
        self._station._view_cursor(self._run_id, x_px, y_px, fps)

    def add_trial(self, row: dict[str, Any]) -> None:
        self._station._view_trial(self._run_id, row)

    def set_blocks(self, blocks: list[dict[str, Any]]) -> None:
        self._station._view_blocks(self._run_id, blocks)

    def close(self) -> None:
        return None


# ----------------------------------------------------------------------
# HTTP plumbing
# ----------------------------------------------------------------------
def _page() -> bytes:
    return (
        resources.files("web_grid_paradigm").joinpath("dashboard.html").read_bytes()
    )


def _make_handler(station: Station) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "webgrid-station"

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            try:
                if path in ("/", "/index.html"):
                    self._send(HTTPStatus.OK, _page(), "text/html; charset=utf-8")
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
    if host in ("0.0.0.0", "::"):
        logger.warning("the web panel is reachable from other computers")
    if base_config is not None and base_config.lsl_state:
        try:
            station.start_lsl_state()
        except Exception as exc:  # noqa: BLE001 - the panel still works
            logger.warning("could not start the LSL state stream: {}", exc)
    return station
