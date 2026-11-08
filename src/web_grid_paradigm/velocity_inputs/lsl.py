"""LSL velocity strategy: an external decoder drives the cursor.

The decoder publishes one LSL stream of floats.  The default wire format is
``[timestamp, vx, vy]``; an optional fourth channel carries a button number
(0 = released, 1/2/3 = click) so click selection works as well.  Velocities
are normalised window units per second (``1.0`` = half the window per
second); the timestamp channel is informational, samples are stamped at
receipt on the runner clock.

The inlet is injectable (``inlet=...``) so the strategy can be unit-tested
without a running LSL stream; ``open()`` resolves the stream by name and
falls back to the stream type when the name is empty.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from loguru import logger

from .base import (
    DeviceContext,
    VelocityCapabilities,
    VelocityFrame,
    VelocitySample,
    VelocitySourceStatus,
    VelocitySourceUnavailable,
)
from .registry import register_velocity_source


@dataclass(frozen=True, slots=True)
class LslVelocityOptions:
    """Configuration of the LSL velocity strategy."""

    stream_name: str = "WebGridVelocity"
    stream_type: str = "Velocity"
    resolve_timeout: float = 5.0
    stale_after: float = 1.0
    channels: int = 3
    max_samples_per_read: int = 256

    def __post_init__(self) -> None:
        if not self.stream_name.strip() and not self.stream_type.strip():
            raise ValueError("LSL velocity needs a stream name or type")
        if self.resolve_timeout <= 0:
            raise ValueError("resolve_timeout must be positive")
        if self.stale_after <= 0:
            raise ValueError("stale_after must be positive")
        if self.channels < 2:
            raise ValueError("LSL velocity needs at least vx/vy channels")
        if self.max_samples_per_read <= 0:
            raise ValueError("max_samples_per_read must be positive")


@register_velocity_source("lsl")
class LslVelocitySource:
    """Velocity samples and optional button edges from an LSL control stream."""

    name = "lsl"
    capabilities = VelocityCapabilities(
        category="lsl", continuous=True, absolute=False, clicks=True
    )

    def __init__(
        self,
        *,
        options: LslVelocityOptions | None = None,
        context: DeviceContext | None = None,
        inlet: Any | None = None,
    ) -> None:
        self.options = options or LslVelocityOptions()
        self.context = context
        self._inlet = inlet
        self._opened = False
        self._prev_button = 0
        self._last_rx: float | None = None
        self._last_read_now: float | None = None
        self._opened_at: float | None = None
        self._frames = 0
        self._invalid = 0
        self._error: str | None = None

    # ------------------------------------------------------------------
    def open(self) -> None:
        if self._opened:
            return
        if self._inlet is None:
            try:
                from pylsl import StreamInlet, resolve_byprop
            except ImportError as exc:  # pragma: no cover - declared dependency
                raise VelocitySourceUnavailable(
                    "pylsl is required for the LSL input strategy"
                ) from exc
            infos: list[Any] = []
            if self.options.stream_name.strip():
                infos = resolve_byprop(
                    "name",
                    self.options.stream_name,
                    timeout=self.options.resolve_timeout,
                )
            if not infos and self.options.stream_type.strip():
                infos = resolve_byprop(
                    "type",
                    self.options.stream_type,
                    timeout=self.options.resolve_timeout,
                )
            if not infos:
                raise VelocitySourceUnavailable(
                    "no LSL velocity stream found: "
                    f"name={self.options.stream_name!r} or "
                    f"type={self.options.stream_type!r} "
                    f"within {self.options.resolve_timeout:g} s"
                )
            self._inlet = StreamInlet(infos[0], max_buflen=360)
        self._opened = True
        self._prev_button = 0
        self._last_rx = None
        self._last_read_now = None
        self._opened_at = time.perf_counter()
        self._error = None

    def close(self) -> None:
        inlet, self._inlet = self._inlet, None
        self._opened = False
        self._opened_at = None
        if inlet is not None:
            try:
                inlet.close_stream()
            except Exception as exc:  # noqa: BLE001 - teardown must not fail
                logger.debug("LSL close_stream failed ({}); trying close()", exc)
                try:
                    inlet.close()
                except Exception as exc2:  # noqa: BLE001
                    logger.debug("could not close the LSL inlet: {}", exc2)

    def reset(self) -> None:
        self._prev_button = 0

    # ------------------------------------------------------------------
    def read(self, now: float) -> VelocityFrame:
        if not self._opened or self._inlet is None:
            return VelocityFrame()
        latest: tuple[float, float] | None = None
        clicks: list[int] = []
        for _ in range(self.options.max_samples_per_read):
            try:
                sample, _stamp = self._inlet.pull_sample(timeout=0.0)
            except Exception as exc:  # noqa: BLE001 - lost stream
                self._error = f"{type(exc).__name__}: {exc}"
                break
            if not sample:
                break
            parsed = self._parse_sample(sample, clicks)
            if parsed is not None:
                latest = parsed

        self._frames += 1
        samples: tuple[VelocitySample, ...] = ()
        if latest is not None:
            self._last_rx = now
            samples = (VelocitySample(now, latest[0], latest[1]),)
        self._last_read_now = now
        return VelocityFrame(samples=samples, clicks=tuple(clicks))

    def _parse_sample(
        self, sample: list[float], clicks: list[int]
    ) -> tuple[float, float] | None:
        try:
            # Default layout: [timestamp, vx, vy, button?].  A two-channel
            # stream without timestamp is accepted as [vx, vy].
            if len(sample) >= 3:
                vx = float(sample[1])
                vy = float(sample[2])
                button = int(sample[3]) if len(sample) >= 4 else 0
            else:
                vx = float(sample[0])
                vy = float(sample[1])
                button = 0
        except (TypeError, ValueError, IndexError):
            self._invalid += 1
            return None
        if button > 0 and button != self._prev_button:
            clicks.append(button)
        self._prev_button = max(0, button)
        return vx, vy

    # ------------------------------------------------------------------
    def button_pressed(self) -> bool:
        return self._prev_button > 0

    def status(self) -> VelocitySourceStatus:
        stale = False
        if self._last_read_now is not None and self._last_rx is not None:
            stale = (
                self._last_read_now - self._last_rx
            ) > self.options.stale_after
        elif self._opened_at is not None:
            stale = (
                time.perf_counter() - self._opened_at
            ) > self.options.stale_after
        return VelocitySourceStatus(
            name=self.name,
            category=self.capabilities.category,
            connected=self._opened,
            device={
                "stream": self.options.stream_name,
                "type": self.options.stream_type,
                "channels": str(self.options.channels),
            },
            last_rx=self._last_rx,
            latency_ms=(
                max(0.0, (self._last_read_now - self._last_rx) * 1000.0)
                if self._last_read_now is not None and self._last_rx is not None
                else None
            ),
            frames=self._frames,
            invalid=self._invalid,
            stale=stale,
            error=self._error,
        )
