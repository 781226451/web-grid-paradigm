"""Parameter form: the single source of truth for the page and validation.

The page renders itself from :func:`form_schema`; submitted values are
converted and validated by :func:`coerce_params` before a run may start.
"""

from __future__ import annotations

from typing import Any

from ..core.config import ExperimentConfig
from ..core.settings import THEMES

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
     "options": ["mouse", "demo", "joystick", "lsl"], "group": "输入"},
    # Device-specific fields are not shown inline: the "输入设备" card opens a
    # dialog with only the fields marked for the selected mode.
    {"name": "demo_speed", "label": "autopilot 速度", "type": "float", "min": 0.1,
     "max": 20, "step": 0.1, "group": "输入", "dialog": "demo"},
    {"name": "joystick_port", "label": "串口", "type": "text",
     "group": "输入", "dialog": "joystick", "hint": "如 COM4"},
    {"name": "joystick_baud", "label": "波特率", "type": "int", "min": 300,
     "max": 2000000, "group": "输入", "dialog": "joystick"},
    {"name": "joystick_address", "label": "总线地址", "type": "int", "min": 0,
     "max": 64, "group": "输入", "dialog": "joystick",
     "hint": "0 = 通用 9 字节帧；1–64 = 总线模式"},
    {"name": "joystick_stream_mode", "label": "发送模式", "type": "choice",
     "options": ["periodic", "on_change"], "group": "输入",
     "dialog": "joystick"},
    {"name": "joystick_speed", "label": "满偏速度 (px/s)", "type": "float",
     "min": 1, "max": 5000, "step": 10, "group": "输入", "dialog": "joystick"},
    {"name": "joystick_deadzone", "label": "死区 (0–0.95)", "type": "float",
     "min": 0, "max": 0.95, "step": 0.05, "group": "输入",
     "dialog": "joystick"},
    {"name": "joystick_invert_x", "label": "X 反向", "type": "bool",
     "group": "输入", "dialog": "joystick"},
    {"name": "joystick_invert_y", "label": "Y 反向", "type": "bool",
     "group": "输入", "dialog": "joystick"},
    {"name": "joystick_center_on_open", "label": "打开时校准中心", "type": "bool",
     "group": "输入", "dialog": "joystick"},
    {"name": "joystick_stale_after", "label": "无帧超时 (s)", "type": "float",
     "min": 0.05, "max": 10, "step": 0.05, "group": "输入",
     "dialog": "joystick", "hint": "periodic 模式超过该时长无帧则停住光标"},
    {"name": "lsl_velocity_stream", "label": "速度流名称", "type": "text",
     "group": "输入", "dialog": "lsl"},
    {"name": "lsl_velocity_type", "label": "速度流类型", "type": "text",
     "group": "输入", "dialog": "lsl"},
    {"name": "lsl_velocity_timeout", "label": "解析超时 (s)", "type": "float",
     "min": 0.1, "max": 60, "step": 0.5, "group": "输入", "dialog": "lsl"},
    {"name": "lsl_velocity_stale_after", "label": "无样本超时 (s)", "type": "float",
     "min": 0.1, "max": 60, "step": 0.1, "group": "输入", "dialog": "lsl"},
    # display
    {"name": "theme", "label": "视觉主题", "type": "choice",
     "options": list(THEMES), "group": "显示"},
    {"name": "fullscreen", "label": "全屏运行", "type": "bool", "group": "显示"},
    {"name": "window_width", "label": "窗口宽", "type": "int", "min": 640,
     "max": 7680, "group": "显示"},
    {"name": "window_height", "label": "窗口高", "type": "int", "min": 480,
     "max": 4320, "group": "显示"},
    {"name": "auto_exit", "label": "结束后自动关闭", "type": "bool", "group": "显示"},
    # markers / LSL
    {"name": "lsl", "label": "发布 LSL 标记", "type": "bool", "group": "标记"},
    {"name": "lsl_stream", "label": "标记流名称", "type": "text", "group": "标记"},
    # --- reward part 1: the external device -----------------------------
    # Port, baud rate and command template are protocol details of the device,
    # so they are asked for in the "连接…" dialog instead of the form.
    {"name": "reward", "label": "交付方式", "type": "choice",
     "options": ["serial", "test", "off"], "group": "奖励设备",
     "hint": "serial = 用已连接的串口设备；test = 只写文件；off = 不发"},
    # --- reward part 2: the schedule ------------------------------------
    {"name": "reward_policy", "label": "发放策略", "type": "choice",
     "options": ["per_hit", "ratio", "none"], "group": "奖励策略",
     "hint": "per_hit = 每次命中；ratio = 每 N 次命中；none = 不发"},
    {"name": "reward_ratio", "label": "每 N 次命中 (ratio)", "type": "int",
     "min": 1, "max": 100, "group": "奖励策略"},
    {"name": "reward_amount", "label": "每次奖励量", "type": "int", "min": 0,
     "max": 255, "group": "奖励策略", "hint": "0 = 不发奖励"},
    {"name": "reward_duration_ms", "label": "奖励脉冲 (ms)", "type": "int",
     "min": 0, "max": 5000, "group": "奖励策略"},
]
_FORM_BY_NAME = {field["name"]: field for field in _FORM}
# Reward sits right after the task section: it is an experiment-level setting,
# and the two parts (device / schedule) are read together.
_FORM_GROUPS = ["会话", "实验设计", "任务", "奖励设备", "奖励策略",
                "输入", "显示", "标记"]


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
