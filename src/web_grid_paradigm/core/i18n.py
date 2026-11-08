"""Small bilingual text catalogue for the experiment UI."""

from __future__ import annotations

STRINGS: dict[str, dict[str, str]] = {
    "zh": {
        "title": "BCI Web-Grid",
        "subtitle": "脑机接口网格目标选择范式",
        "instr_click": "把光标移动到蓝色目标格上，然后点击。",
        "instr_click_multi": "目标颜色对应按键：蓝色=左键，橙色=右键，紫色=中键。\n把光标移到目标格，按对应按键点击。",
        "instr_dwell": "把光标移动到蓝色目标格上并停留。\n停留时间达到设定值即命中。",
        "instr_formula": "得分 = 每分钟净命中数 × log2(网格数 × 点击类型数)",
        "mode_mouse": "输入：鼠标（用于本地调试）",
        "mode_demo": "输入：演示模式（光标自动移动）",
        "mode_joystick": "输入：串口摇杆（{port}）",
        "mode_lsl": "输入：LSL 速度流（{stream}）",
        "start_hint": "空格 / 点击 开始        Esc 退出",
        "progress": "目标 {current} / {total}",
        "score": "得分 {bps:.2f} BPS",
        "errors": "错误 {errors}",
        "meta_grid": "{rows}×{cols}   ·   NTPM {ntpm:.1f}",
        "hint_click": "点击蓝色目标",
        "hint_click_multi": "按目标颜色点击对应按键",
        "hint_dwell": "停留在蓝色目标 {dwell:.1f} 秒",
        "legend_left": "左键",
        "legend_right": "右键",
        "legend_middle": "中键",
        "feedback_hit": "命中",
        "feedback_miss": "未命中，再试一次",
        "feedback_timeout": "超时，进入下一个目标",
        "done_title": "本组完成",
        "done_stats": "命中 {hits}   ·   错误 {errors}   ·   超时 {timeouts}\n"
        "正确率 {accuracy:.0%}   ·   平均用时 {rt}\n"
        "净命中/分钟 {ntpm:.1f}   ·   得分 {bps:.2f} BPS",
        "saved": "数据已保存：{path}",
        "exit_hint": "按 空格 退出",
        "aborted": "已中止，部分数据已保存",
        "countdown_go": "开始",
        "score_zero": "得分 0.00 BPS",
        "get_ready": "准备开始…",
    },
    "en": {
        "title": "BCI Web-Grid",
        "subtitle": "A grid target-selection paradigm for brain-computer interfaces",
        "instr_click": "Move the cursor onto a blue target cell, then click.",
        "instr_click_multi": "Target colour maps to a button: blue=left, orange=right, purple=middle.\n"
        "Move onto the target and press the matching button.",
        "instr_dwell": "Move the cursor onto a blue target cell and hold it there.\n"
        "The target is selected after the dwell time.",
        "instr_formula": "Score = net targets per minute × log2(grid cells × click types)",
        "mode_mouse": "Input: mouse (local testing)",
        "mode_demo": "Input: demo autopilot",
        "mode_joystick": "Input: serial joystick ({port})",
        "mode_lsl": "Input: LSL velocity stream ({stream})",
        "start_hint": "Space / click to start        Esc to quit",
        "progress": "Target {current} / {total}",
        "score": "{bps:.2f} BPS",
        "errors": "Errors {errors}",
        "meta_grid": "{rows}×{cols}   ·   NTPM {ntpm:.1f}",
        "hint_click": "Click the blue target",
        "hint_click_multi": "Click with the button matching the target colour",
        "hint_dwell": "Hold on the blue target for {dwell:.1f} s",
        "legend_left": "Left click",
        "legend_right": "Right click",
        "legend_middle": "Middle click",
        "feedback_hit": "Hit",
        "feedback_miss": "Missed, try again",
        "feedback_timeout": "Timeout, next target",
        "done_title": "Block complete",
        "done_stats": "Hits {hits}   ·   Errors {errors}   ·   Timeouts {timeouts}\n"
        "Accuracy {accuracy:.0%}   ·   Mean time {rt}\n"
        "Net targets/min {ntpm:.1f}   ·   Score {bps:.2f} BPS",
        "saved": "Data saved to: {path}",
        "exit_hint": "Press space to exit",
        "aborted": "Aborted, partial data saved",
        "countdown_go": "Go",
        "score_zero": "Score 0.00 BPS",
        "get_ready": "Get ready…",
    },
}

for _lang, _table in STRINGS.items():
    if set(_table) != set(STRINGS["zh"]):
        raise RuntimeError(f"i18n tables differ for {_lang}")


class Strings:
    def __init__(self, language: str) -> None:
        try:
            self._table = STRINGS[language]
        except KeyError as exc:  # pragma: no cover - validated earlier
            raise ValueError(f"unknown language {language!r}") from exc

    def __getitem__(self, key: str) -> str:
        return self._table[key]

    def format(self, key: str, **kwargs: object) -> str:
        return self._table[key].format(**kwargs)
