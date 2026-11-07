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
_INPUT_MODES = ("mouse", "keyboard", "udp", "demo")
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
    targets: int = 40
    max_seconds: float = 300.0
    selection: str = "click"  # click | dwell
    dwell_time: float = 1.0
    trial_timeout: float = 15.0  # 0 disables the per-target timeout
    click_types: int = 1  # 1..3: target colour / required button + score
    feedback: float = 0.35
    countdown_seconds: float = 2.0
    seed: int = 20261107

    # --- input ------------------------------------------------------------
    input: str = "mouse"  # mouse | keyboard | udp | demo
    udp_host: str = "127.0.0.1"
    udp_port: int = 9000
    smoothing: float = 0.0  # 0 raw ... 0.95 very smooth (UDP only)
    keyboard_step: float = 0.035  # normalised units per key press
    demo_speed: float = 2.2  # normalised units per second

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

    def __post_init__(self) -> None:
        if isinstance(self.output_dir, str):
            object.__setattr__(self, "output_dir", Path(self.output_dir))

    # ------------------------------------------------------------------
    @classmethod
    def from_toml(cls, path: str | Path) -> ExperimentConfig:
        """Load a configuration from a TOML file.

        Both a top-level table and a ``[webgrid]`` table are accepted.
        Unknown keys are rejected so typos cannot silently change a session.
        """
        path = Path(path)
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        table = data.get("webgrid", data)
        if not isinstance(table, Mapping):
            raise TypeError(f"{path}: [webgrid] must be a table")
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
        if self.targets < 1:
            raise ValueError("targets must be >= 1")
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
        if not 0 <= self.countdown_seconds <= 10:
            raise ValueError("countdown_seconds must be between 0 and 10 s")
        if self.input not in _INPUT_MODES:
            raise ValueError(f"input must be one of {_INPUT_MODES}")
        if not 1 <= self.udp_port <= 65535:
            raise ValueError("udp_port must be between 1 and 65535")
        if not 0 <= self.smoothing <= 0.95:
            raise ValueError("smoothing must be between 0 and 0.95")
        if not 0 < self.keyboard_step <= 0.5:
            raise ValueError("keyboard_step must be in (0, 0.5]")
        if self.demo_speed <= 0:
            raise ValueError("demo_speed must be > 0")
        if self.window_width < 640 or self.window_height < 480:
            raise ValueError("window must be at least 640x480")
        if self.marker_udp:
            host, _, port = self.marker_udp.rpartition(":")
            if not host or not port.isdigit() or not 1 <= int(port) <= 65535:
                raise ValueError("marker_udp must look like '127.0.0.1:9001'")
        if not self.lsl_stream.strip():
            raise ValueError("lsl_stream must not be empty")

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

    def to_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        data["output_dir"] = str(self.output_dir)
        return data
