"""Reward delivery — the *how* module.

Takes an already-made decision (amount + pulse length) and gets it to the
hardware.  It knows nothing about trial results or schedules.

``serial``  (default) one ASCII command line per reward over a serial port,
            written by a background thread so the render loop never blocks on
            UART timing.
``test``    no hardware: the exact bytes that would be sent are appended to
            ``reward_out.txt`` in the session directory and logged, so the
            protocol can be verified before an Arduino is attached.
``off``     discard rewards entirely (behaviour-only sessions).

If the serial port cannot be opened the session still runs: the factory falls
back to ``test`` and logs an error, so a missing Arduino never kills a session.
"""

from __future__ import annotations

import threading
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Protocol

from loguru import logger

DEFAULT_COMMAND = "R {amount} {duration_ms}\n"
DEFAULT_BAUD = 9600
REWARD_MODES = ("serial", "test", "off")


def format_command(template: str, amount: int, duration_ms: int) -> str:
    """Render the wire command for one reward."""
    return template.format(amount=int(amount), duration_ms=int(duration_ms))


class RewardSink(Protocol):
    """Strategy interface for *how* a reward reaches the hardware."""

    name: str

    def deliver(self, amount: int, duration_ms: int, reason: str = "") -> None: ...

    def close(self) -> None: ...


class NullRewardSink:
    """Rewards disabled."""

    name = "off"

    def deliver(self, amount: int, duration_ms: int, reason: str = "") -> None:
        return None

    def close(self) -> None:
        return None


class DryRunRewardSink:
    """Dry run: records the serial bytes instead of sending them."""

    name = "test"

    def __init__(
        self,
        directory: Path | None = None,
        command: str = DEFAULT_COMMAND,
    ) -> None:
        self.command = command
        self.path: Path | None = None
        if directory is not None:
            directory.mkdir(parents=True, exist_ok=True)
            self.path = directory / "reward_out.txt"
        self.sent = 0

    def deliver(self, amount: int, duration_ms: int, reason: str = "") -> None:
        text = format_command(self.command, amount, duration_ms)
        self.sent += 1
        logger.info(
            "[reward:test] {} <- amount={} duration={}ms reason={}",
            text.rstrip("\n"),
            amount,
            duration_ms,
            reason or "-",
        )
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()

    def close(self) -> None:
        return None


class SerialRewardSink:
    """Serial (UART) strategy, default target: an Arduino sketch.

    ``deliver`` only enqueues the command; a writer thread owns the port, so a
    slow or stalled serial link cannot stretch a video frame.
    """

    name = "serial"

    def __init__(
        self,
        port: str,
        baud: int = DEFAULT_BAUD,
        command: str = DEFAULT_COMMAND,
        *,
        write_timeout: float = 1.0,
    ) -> None:
        self.port = port
        self.baud = int(baud)
        self.command = command
        self.sent = 0
        self.errors = 0
        self._serial = _open_serial(port, self.baud, write_timeout)
        self._queue: Queue[str] = Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._write_loop, name="webgrid-reward-serial", daemon=True
        )
        self._thread.start()
        logger.info("reward serial port {} open at {} baud", port, self.baud)

    def deliver(self, amount: int, duration_ms: int, reason: str = "") -> None:
        text = format_command(self.command, amount, duration_ms)
        self._queue.put(text)
        self.sent += 1
        logger.debug(
            "[reward:serial] queued {!r} (amount={} reason={})",
            text.rstrip("\n"),
            amount,
            reason or "-",
        )

    def _write_loop(self) -> None:
        while not self._stop.is_set():
            try:
                text = self._queue.get(timeout=0.1)
            except Empty:
                continue
            try:
                self._serial.write(text.encode("ascii", "replace"))
                self._serial.flush()
            except Exception as exc:  # noqa: BLE001 - never kill the session
                self.errors += 1
                logger.error("could not send reward {!r}: {}", text.rstrip(), exc)

    def close(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)
        try:
            self._serial.close()
        except Exception as exc:  # noqa: BLE001 - teardown must not fail
            logger.debug("could not close the reward port: {}", exc)


def _open_serial(port: str, baud: int, write_timeout: float) -> Any:
    """Indirection point so tests can supply a fake serial port."""
    import serial  # imported here: pyserial is only needed for this strategy

    return serial.Serial(
        port=port, baudrate=baud, timeout=0, write_timeout=write_timeout
    )


def build_reward_sink(config: Any, directory: Path | None = None) -> RewardSink:
    """Pick and build the delivery strategy named in the configuration."""
    mode = getattr(config, "reward", "off")
    command = getattr(config, "reward_command", DEFAULT_COMMAND)
    if mode == "off":
        logger.info("rewards disabled")
        return NullRewardSink()
    if mode == "test":
        logger.info("reward sink: test (no hardware)")
        return DryRunRewardSink(directory, command)
    if mode != "serial":
        raise ValueError(f"unknown reward mode: {mode!r}")
    try:
        return SerialRewardSink(
            getattr(config, "reward_port", "COM3"),
            getattr(config, "reward_baud", DEFAULT_BAUD),
            command,
        )
    except Exception as exc:  # noqa: BLE001 - hardware is optional
        logger.error(
            "reward serial port {} unavailable ({}); falling back to test mode",
            getattr(config, "reward_port", "COM3"),
            exc,
        )
        return DryRunRewardSink(directory, command)
