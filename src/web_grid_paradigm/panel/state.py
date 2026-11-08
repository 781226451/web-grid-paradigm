"""Panel state: the run queue, the live snapshot and the per-run view.

The HTTP server (see :mod:`.server`) only reads and writes this object; the
render loop talks to it through :class:`SessionView`.  Everything is guarded
by one condition variable, so the render loop never blocks on the network.
"""

from __future__ import annotations

import json
import socket
import threading
import time
import webbrowser
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from loguru import logger

from ..config import ExperimentConfig
from ..reward.sink import (
    DryRunRewardSink,
    SerialRewardSink,
    format_command,
    serial_ports,
)
from .lsl_state import LslStatePublisher
from .schema import _FORM_BY_NAME, _FORM_GROUPS, coerce_params, form_schema
from .server import _make_handler, _Server

# Fields the "test reward" button may override.  Port and baud rate belong to
# the connected device (set in the dialog), so they are not listed here.
_REWARD_TEST_KEYS = (
    "reward",
    "reward_amount",
    "reward_duration_ms",
)

# Addresses that make the server listen on every interface / only on loopback.
_WILDCARD_HOSTS = frozenset({"", "0.0.0.0", "::", "[::]"})
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})


def is_wildcard(host: str) -> bool:
    """True when ``host`` binds every interface, i.e. other computers can connect."""
    return host.strip().lower() in _WILDCARD_HOSTS


def lan_ipv4_addresses() -> list[str]:
    """IPv4 addresses of this computer that another computer can reach.

    The default-route address comes first.  A machine with Hyper-V, WSL or
    VPN adapters resolves its own host name to several addresses, and the
    virtual-switch ones cannot be reached from the lab network.  Loopback and
    link-local (169.254/16) addresses are dropped: they never help a remote
    browser.
    """
    found: list[str] = []

    def add(address: str) -> None:
        if address not in found and not address.startswith(("127.", "169.254.")):
            found.append(address)

    # A connected UDP socket reports the address of the default route without
    # sending a single packet (192.0.2.0/24 is TEST-NET-1, never routed).
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))
            add(probe.getsockname()[0])
    except OSError:
        pass
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        infos = []
    for info in infos:
        add(str(info[4][0]))
    return found


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
        # Reward device opened from the panel (optional).  When connected it is
        # shared by every session until the experimenter disconnects.
        self._reward_device: SerialRewardSink | None = None
        self._reward_port = self.base_config.reward_port
        self._reward_baud = self.base_config.reward_baud
        self._reward_error: str | None = None

        self._server = _Server((host, port), _make_handler(self))
        self.host = host
        self.port = int(self._server.server_address[1])
        self._wildcard = is_wildcard(host)
        self._loopback = host.strip().lower() in _LOOPBACK_HOSTS
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="webgrid-station", daemon=True
        )
        self._thread.start()
        if open_browser:
            webbrowser.open(self.url)

    # ------------------------------------------------------------------
    @property
    def url(self) -> str:
        """The URL to use *on this computer* (loopback when bound to all interfaces)."""
        host = "127.0.0.1" if self._wildcard else self.host.strip()
        if ":" in host and not host.startswith("["):  # bare IPv6 literal
            host = f"[{host}]"
        return f"http://{host}:{self.port}/"

    @property
    def lan_urls(self) -> list[str]:
        """URLs a browser on another computer can use.

        Empty when the panel only listens on loopback; the default-route
        address comes first.
        """
        if not self._wildcard:
            return []
        return [f"http://{address}:{self.port}/" for address in lan_ipv4_addresses()]

    @property
    def is_wildcard(self) -> bool:
        return self._wildcard

    @property
    def is_loopback(self) -> bool:
        return self._loopback

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
            "options": {"reward_port": serial_ports()},
        }

    def _base_values(self) -> dict[str, Any]:
        data = self.base_config.to_dict()
        data["output_dir"] = str(self.base_config.output_dir)
        return {name: data[name] for name in _FORM_BY_NAME}

    # --- reward hardware --------------------------------------------------
    # --- reward device (connect / disconnect from the page) ---------------
    def reward_device(self) -> SerialRewardSink | None:
        """The connected serial device, if any (sessions share it)."""
        with self._cond:
            return self._reward_device

    def reward_status(self) -> dict[str, Any]:
        with self._cond:
            device = self._reward_device
            return {
                "connected": device is not None,
                "port": self._reward_port,
                "baud": self._reward_baud,
                "sent": device.sent if device is not None else 0,
                "errors": device.errors if device is not None else 0,
                "error": self._reward_error,
                "ports": serial_ports(),
            }

    def connect_reward(
        self, port: str | None = None, baud: int | None = None
    ) -> dict[str, Any]:
        """Open the serial reward device (used by every session afterwards).

        ``port`` and ``baud`` are the only device settings: the wire command is
        built into the protocol (see :data:`web_grid_paradigm.reward.sink.WIRE_COMMAND`).
        """
        port = (port or self._reward_port or "").strip()
        try:
            baud = int(baud if baud is not None else self._reward_baud)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"波特率无效: {baud!r}") from exc
        if not port:
            raise ValueError("串口不能为空")
        if not 300 <= baud <= 2_000_000:
            raise ValueError("波特率必须在 300–2000000 之间")
        self.disconnect_reward()
        try:
            device = SerialRewardSink(port, baud)
        except Exception as exc:
            with self._cond:
                self._reward_error = str(exc)
                self._bump()
            raise ValueError(f"无法打开串口 {port}: {exc}") from exc
        with self._cond:
            self._reward_device = device
            self._reward_port = port
            self._reward_baud = baud
            self._reward_error = None
            self._bump()
        logger.info("reward device connected: {} @ {} baud", port, baud)
        return self.reward_status()

    def disconnect_reward(self) -> dict[str, Any]:
        with self._cond:
            device = self._reward_device
            self._reward_device = None
            self._bump()
        if device is not None:
            device.close()
            logger.info("reward device {} disconnected", device.port)
        return self.reward_status()

    def reward_self_test(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send one pulse with the panel's reward settings (no session needed).

        Uses the connected device when there is one, otherwise a dry run
        (``reward = test``).  Unlike a real run this does *not* open the port
        implicitly or fall back to ``test``: a failed wiring check must be
        visible.
        """
        keys = {k: v for k, v in payload.items() if k in _REWARD_TEST_KEYS}
        config = coerce_params(keys, self.base_config)
        with self._cond:
            device = self._reward_device
        if config.reward == "off":
            return {"ok": True, "sink": "off", "detail": "奖励已关闭，未发送"}
        if device is not None:
            sink: Any = device
            port = device.port
        elif config.reward == "test":
            sink, port = DryRunRewardSink(None), ""
        else:
            raise ValueError("串口奖励设备未连接：请先在“奖励设备”里连接串口")
        sink.deliver(config.reward_amount, config.reward_duration_ms, "self-test")
        logger.info(
            "reward self-test: {} via {} ({} unit / {} ms)",
            format_command(config.reward_amount, config.reward_duration_ms).rstrip(),
            sink.name,
            config.reward_amount,
            config.reward_duration_ms,
        )
        with self._cond:
            self._bump()
        return {
            "ok": True,
            "sink": sink.name,
            "port": port,
            "command": format_command(
                config.reward_amount, config.reward_duration_ms
            ).rstrip("\n"),
        }

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
            "reward_device": self.reward_status(),
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
        self.disconnect_reward()
        if self._sink_id is not None:
            try:
                logger.remove(self._sink_id)
            except ValueError:
                pass
            self._sink_id = None
        self._server.shutdown()
        self._server.server_close()


class SessionView:
    """Per-run monitoring handle handed to the renderer."""

    def __init__(self, station: Station, run_id: int) -> None:
        self._station = station
        self._run_id = run_id

    @property
    def stop_requested(self) -> bool:
        return self._station._stop.is_set()

    @property
    def reward_sink(self) -> SerialRewardSink | None:
        """The reward device connected from the panel, if any."""
        return self._station.reward_device()

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
