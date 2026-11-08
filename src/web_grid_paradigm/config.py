"""Experiment configuration for the BCI web-grid paradigm.

The configuration is deliberately a plain frozen dataclass so that every
setting is explicit, validated once, and easy to serialise next to the data.
Settings can come from a TOML file, the command line, or both (the command
line wins).
"""

from __future__ import annotations

import dataclasses
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

_SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_INPUT_MODES = ("mouse", "demo", "joystick", "lsl")
_JOYSTICK_STREAM_MODES = ("periodic", "on_change")
_SELECTION_MODES = ("click", "dwell")
_LANGUAGES = ("zh", "en")


@dataclass(frozen=True, slots=True)
class ExperimentConfig:
    """All parameters of one experimental session."""

    # --- identity / files -------------------------------------------------
    subject: str = "sub-01"
    session: str = ""  # empty -> local timestamp
    output_dir: Path = field(default_factory=lambda: Path("data"))
    language: str = "zh"
    font: str = "Microsoft YaHei"

    # --- grid / task ------------------------------------------------------
    rows: int = 12
    cols: int = 12
    blocks: int = 1  # number of blocks in the session
    targets: int = 40  # trials (targets) per block
    block_rest: float = 10.0  # blank rest between blocks, seconds
    max_seconds: float = 300.0  # per-block time limit; 0 disables
    selection: str = "click"  # click | dwell
    dwell_time: float = 1.0
    trial_timeout: float = 15.0  # 0 disables the per-target timeout
    click_types: int = 1  # 1..3: target colour / required button + score
    feedback: float = 0.35
    iti: float = 0.0  # inter-trial rest (blank grid, no target) after feedback
    countdown_seconds: float = 2.0
    seed: int = 20261107

    # --- input ------------------------------------------------------------
    input: str = "mouse"  # mouse | demo | joystick | lsl
    demo_speed: float = 2.2  # normalised units per second

    # serial hall-effect joystick (input = "joystick")
    joystick_port: str = ""  # e.g. COM4 (Windows) or /dev/ttyUSB0
    joystick_baud: int = 9600
    joystick_address: int = 0  # 0 = universal 9-byte frame; 1..64 = bus mode
    joystick_stream_mode: str = "periodic"  # periodic | on_change
    joystick_speed: float = 560.0  # pixels/s at full deflection
    joystick_deadzone: float = 0.0  # normalised dead zone, 0 = off
    joystick_invert_x: bool = False
    joystick_invert_y: bool = False
    joystick_center_on_open: bool = False  # send the set-centre command
    joystick_stale_after: float = 0.4  # periodic stream watchdog, seconds

    # LSL velocity decoder (input = "lsl")
    lsl_velocity_stream: str = "WebGridVelocity"
    lsl_velocity_type: str = "Velocity"
    lsl_velocity_timeout: float = 5.0  # resolve timeout, seconds
    lsl_velocity_stale_after: float = 1.0

    # --- display ----------------------------------------------------------
    fullscreen: bool = True
    window_width: int = 1280
    window_height: int = 800
    screen: int = 0
    hide_cursor: bool = True
    skip_instructions: bool = True
    auto_exit: bool = False

    # --- event markers ----------------------------------------------------
    marker_udp: str = ""  # "host:port"; empty disables UDP markers
    lsl: bool = False
    lsl_stream: str = "WebGridMarkers"

    # --- LSL state stream (started from the web panel) -------------------
    lsl_state: bool = False  # publish the state stream automatically
    lsl_state_stream: str = "WebGridState"
    lsl_state_rate: float = 10.0  # snapshots per second

    # --- reward -----------------------------------------------------------
    # Two orthogonal strategies: reward_policy decides *when*, reward decides
    # *how* the pulse reaches the hardware.
    reward: str = "serial"  # serial | test | off
    reward_policy: str = "per_hit"  # per_hit | ratio | none
    reward_ratio: int = 2  # used by the "ratio" policy (FR-n)
    reward_port: str = "COM3"
    reward_baud: int = 9600
    reward_amount: int = 1  # units handed out per hit
    reward_duration_ms: int = 50  # pulse length passed to the Arduino

    # --- live web dashboard -----------------------------------------------
    dashboard: bool = True
    dashboard_host: str = "127.0.0.1"  # "0.0.0.0" = reachable from the LAN
    dashboard_port: int = 8765
    dashboard_open: bool = True  # open a browser tab automatically

    def __post_init__(self) -> None:
        if isinstance(self.output_dir, str):
            object.__setattr__(self, "output_dir", Path(self.output_dir))

    # ------------------------------------------------------------------
    @classmethod
    def from_toml(cls, path: str | Path) -> ExperimentConfig:
        """Load a configuration from a TOML file.

        Accepted shapes::

            rows = 12                  # flat
            [webgrid]                  # one named table
            rows = 12
            [reward]                   # optional section for hardware keys
            reward_port = "COM3"

        A ``[reward]`` (or ``[webgrid.reward]``) table is folded into the same
        flat namespace, so a single file can hold both the paradigm settings
        and the reward hardware settings.  Unknown keys are rejected so typos
        cannot silently change a session.
        """
        path = Path(path)
        data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
        table = data.get("webgrid", data)
        if not isinstance(table, Mapping):
            raise TypeError(f"{path}: [webgrid] must be a table")
        table = _merge_reward_table(table, path)
        known = {f.name for f in dataclasses.fields(cls)}
        unknown = sorted(set(table) - known)
        if unknown:
            raise ValueError(
                f"{path}: unknown configuration key(s): {', '.join(unknown)}"
            )
        try:
            cfg = cls(**dict(table))
        except TypeError as exc:  # pragma: no cover - defensive
            raise ValueError(f"{path}: {exc}") from exc
        cfg.validate()
        return cfg

    # ------------------------------------------------------------------
    def validate(self) -> None:
        """Raise ``ValueError`` when a setting cannot produce a valid run."""
        if not _SAFE_LABEL.match(self.subject):
            raise ValueError("subject must match [A-Za-z0-9][A-Za-z0-9._-]*")
        if self.session and not _SAFE_LABEL.match(self.session):
            raise ValueError("session must match [A-Za-z0-9][A-Za-z0-9._-]*")
        if self.language not in _LANGUAGES:
            raise ValueError(f"language must be one of {_LANGUAGES}")
        if not self.font.strip():
            raise ValueError("font must not be empty")
        if not 2 <= self.rows <= 40:
            raise ValueError("rows must be between 2 and 40")
        if not 2 <= self.cols <= 40:
            raise ValueError("cols must be between 2 and 40")
        if not 1 <= self.blocks <= 100:
            raise ValueError("blocks must be between 1 and 100")
        if self.targets < 1:
            raise ValueError("targets (trials per block) must be >= 1")
        if not 0 <= self.block_rest <= 600:
            raise ValueError("block_rest must be between 0 and 600 s")
        if self.max_seconds < 0:
            raise ValueError("max_seconds must be >= 0")
        if self.selection not in _SELECTION_MODES:
            raise ValueError(f"selection must be one of {_SELECTION_MODES}")
        if self.selection == "dwell":
            if self.dwell_time <= 0:
                raise ValueError("dwell_time must be > 0 in dwell mode")
            if self.trial_timeout > 0 and self.trial_timeout <= self.dwell_time:
                raise ValueError("trial_timeout must exceed dwell_time")
        if self.trial_timeout < 0:
            raise ValueError("trial_timeout must be >= 0")
        if not 1 <= self.click_types <= 3:
            raise ValueError("click_types must be between 1 and 3")
        if not 0 <= self.feedback <= 5:
            raise ValueError("feedback must be between 0 and 5 s")
        if not 0 <= self.iti <= 60:
            raise ValueError("iti must be between 0 and 60 s")
        if not 0 <= self.countdown_seconds <= 10:
            raise ValueError("countdown_seconds must be between 0 and 10 s")
        if self.input not in _INPUT_MODES:
            raise ValueError(f"input must be one of {_INPUT_MODES}")
        if self.demo_speed <= 0:
            raise ValueError("demo_speed must be > 0")
        if not 300 <= self.joystick_baud <= 2_000_000:
            raise ValueError("joystick_baud must be between 300 and 2000000")
        if not 0 <= self.joystick_address <= 64:
            raise ValueError("joystick_address must be between 0 and 64")
        if self.joystick_stream_mode not in _JOYSTICK_STREAM_MODES:
            raise ValueError(
                f"joystick_stream_mode must be one of {_JOYSTICK_STREAM_MODES}"
            )
        if self.joystick_speed <= 0:
            raise ValueError("joystick_speed must be > 0")
        if not 0.0 <= self.joystick_deadzone < 1.0:
            raise ValueError("joystick_deadzone must be in [0, 1)")
        if self.joystick_stale_after <= 0:
            raise ValueError("joystick_stale_after must be > 0")
        if self.input == "joystick" and not self.joystick_port.strip():
            raise ValueError("joystick_port must be set when input = 'joystick'")
        if self.lsl_velocity_timeout <= 0:
            raise ValueError("lsl_velocity_timeout must be > 0")
        if self.lsl_velocity_stale_after <= 0:
            raise ValueError("lsl_velocity_stale_after must be > 0")
        if self.input == "lsl" and not (
            self.lsl_velocity_stream.strip() or self.lsl_velocity_type.strip()
        ):
            raise ValueError(
                "lsl_velocity_stream or lsl_velocity_type must be set when "
                "input = 'lsl'"
            )
        if self.window_width < 640 or self.window_height < 480:
            raise ValueError("window must be at least 640x480")
        if self.marker_udp:
            host, _, port = self.marker_udp.rpartition(":")
            if not host or not port.isdigit() or not 1 <= int(port) <= 65535:
                raise ValueError("marker_udp must look like '127.0.0.1:9001'")
        if not self.lsl_stream.strip():
            raise ValueError("lsl_stream must not be empty")
        if not self.lsl_state_stream.strip():
            raise ValueError("lsl_state_stream must not be empty")
        if not 0.5 <= self.lsl_state_rate <= 100:
            raise ValueError("lsl_state_rate must be between 0.5 and 100 Hz")
        if self.lsl_state_stream == self.lsl_stream:
            raise ValueError("lsl_state_stream must differ from lsl_stream")
        if not 0 <= self.dashboard_port <= 65535:
            raise ValueError("dashboard_port must be between 0 and 65535")
        if not self.dashboard_host.strip():
            raise ValueError("dashboard_host must not be empty")
        if self.reward not in ("serial", "test", "off"):
            raise ValueError("reward must be one of ('serial', 'test', 'off')")
        if self.reward_policy not in ("per_hit", "ratio", "none"):
            raise ValueError("reward_policy must be one of ('per_hit', 'ratio', 'none')")
        if not 1 <= self.reward_ratio <= 100:
            raise ValueError("reward_ratio must be between 1 and 100")
        if self.reward == "serial" and not self.reward_port.strip():
            raise ValueError("reward_port must not be empty in serial mode")
        if not 300 <= self.reward_baud <= 2_000_000:
            raise ValueError("reward_baud must be between 300 and 2000000")
        if not 0 <= self.reward_amount <= 255:
            raise ValueError("reward_amount must be between 0 and 255")
        if not 0 <= self.reward_duration_ms <= 5000:
            raise ValueError("reward_duration_ms must be between 0 and 5000")

    # ------------------------------------------------------------------
    @property
    def session_id(self) -> str:
        return self.session or datetime.now().strftime("%Y%m%d-%H%M%S")

    @property
    def data_dir(self) -> Path:
        return self.output_dir / self.subject / f"ses-{self.session_id}"

    @property
    def n_cells(self) -> int:
        return self.rows * self.cols

    @property
    def total_trials(self) -> int:
        return self.blocks * self.targets

    def to_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        data["output_dir"] = str(self.output_dir)
        return data

    def to_toml(self) -> str:
        """Serialise every field as a flat TOML document (``from_toml`` reads it)."""
        lines = ["# BCI Web-Grid configuration", ""]
        for name, value in self.to_dict().items():
            lines.append(f"{name} = {_toml_value(value)}")
        return "\n".join(lines) + "\n"

    def save_toml(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_toml(), encoding="utf-8")
        return path


def _merge_reward_table(table: Mapping[str, Any], path: Path) -> dict[str, Any]:
    """Fold a ``[reward]`` section into the flat key namespace.

    ``reward = "serial"`` (a string) is the ordinary config field, while a
    ``[reward]`` table is the optional hardware section; only the latter is
    flattened.
    """
    reward = table.get("reward")
    if not isinstance(reward, Mapping):
        return dict(table)
    merged = {key: value for key, value in table.items() if key != "reward"}
    merged.update(dict(reward))
    return merged


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'
