"""Configuration scopes used by the CLI, panel and documentation.

The flat :class:`~web_grid_paradigm.core.config.ExperimentConfig` remains the
resolved runtime object.  This module only classifies where each setting
belongs conceptually, so the panel can distinguish editable session values
from startup-only values.
"""

from __future__ import annotations

DEFAULT_SOURCE = "default"
SOURCE_CONFIG = "config"
SOURCE_DEVICE = "device"
SOURCE_CLI = "cli"
SOURCE_WEBUI = "webui"

SCOPE_BOOTSTRAP = "bootstrap"
SCOPE_EXPERIMENT = "experiment"
SCOPE_DEVICE = "device"

# Process/network settings: changing these requires restarting the panel.
BOOTSTRAP_FIELDS = frozenset(
    {
        "dashboard",
        "dashboard_host",
        "dashboard_port",
        "dashboard_open",
    }
)

# Experiment-design settings: safe to edit in the web panel before a run.
EXPERIMENT_FIELDS = frozenset(
    {
        "subject",
        "session",
        "output_dir",
        "language",
        "font",
        "rows",
        "cols",
        "blocks",
        "targets",
        "block_rest",
        "max_seconds",
        "selection",
        "dwell_time",
        "trial_timeout",
        "click_types",
        "feedback",
        "iti",
        "countdown_seconds",
        "seed",
        "input",
        "fullscreen",
        "window_width",
        "window_height",
        "screen",
        "hide_cursor",
        "skip_instructions",
        "auto_exit",
    }
)

# Hardware/decoder settings: machine-local and usually edited in a device
# dialog rather than in the main form.
DEVICE_FIELDS = frozenset(
    {
        "demo_speed",
        "joystick_port",
        "joystick_baud",
        "joystick_address",
        "joystick_stream_mode",
        "joystick_speed",
        "joystick_deadzone",
        "joystick_invert_x",
        "joystick_invert_y",
        "joystick_center_on_open",
        "joystick_stale_after",
        "lsl_velocity_stream",
        "lsl_velocity_type",
        "lsl_velocity_timeout",
        "lsl_velocity_stale_after",
        "lsl",
        "lsl_stream",
        "lsl_state",
        "lsl_state_stream",
        "lsl_state_rate",
        "reward",
        "reward_policy",
        "reward_ratio",
        "reward_port",
        "reward_baud",
        "reward_amount",
        "reward_duration_ms",
    }
)

FIELD_SCOPES: dict[str, str] = {
    **{name: SCOPE_BOOTSTRAP for name in BOOTSTRAP_FIELDS},
    **{name: SCOPE_EXPERIMENT for name in EXPERIMENT_FIELDS},
    **{name: SCOPE_DEVICE for name in DEVICE_FIELDS},
}

# Keys accepted in the main --config file.  Device keys live in the files
# passed with --device-config, one file per module.
CONFIG_FILE_FIELDS: frozenset[str] = EXPERIMENT_FIELDS | BOOTSTRAP_FIELDS
