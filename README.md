# BCI Web-Grid（PsychoPy）

一个基于 **PsychoPy** 的 BCI **web-grid** 离散目标选择范式。屏幕显示网格，每次高亮一个目标格；被试通过 BCI 解码器（或鼠标/键盘）移动光标，并用点击或停留完成选择。程序记录行为数据、计算信息传输率（BPS），并可向 EEG/BCI 采集系统发送事件标记。

> 本仓库负责**刺激呈现、输入接入、行为记录和事件标记**，不包含 EEG 解码算法。解码器通过 UDP 把光标位置和点击发送进来即可。

![界面预览](docs/preview.png)

## 环境

- Python **3.11**（`pyproject.toml` 限定 `>=3.11,<3.12`，`.python-version` 为 `3.11`）
- [uv](https://docs.astral.sh/uv/)
- PsychoPy `2026.2.5`（由 `uv.lock` 锁定）
- Windows 10/11（默认中文字体为 `Microsoft YaHei`）

```powershell
uv sync
uv run webgrid --version
```

可选 LSL 标记（需要额外安装 `pylsl`）：

```powershell
uv sync --extra lsl
```

## 快速开始

```powershell
# 自动演示：无需鼠标，5 个目标后自动退出
uv run webgrid --input demo --targets 5 --auto-exit

# 鼠标调试：移动鼠标，移动到蓝色目标后左键点击
uv run webgrid --input mouse

# 三键模式示例：蓝/橙/紫目标分别对应左/右/中键
uv run webgrid --input mouse --click-types 3

# 人用指导语页（默认关闭；动物实验不需要）
uv run webgrid --input mouse --instructions

# 只渲染一帧界面预览（预览始终窗口模式），不记录数据
uv run webgrid --screenshot docs/preview.png
```

默认全屏运行；本地调试可加 `--windowed`：

```powershell
uv run webgrid --input udp --udp-port 9000 --subject sub-01
uv run webgrid --input mouse --windowed
```

数据默认写入 `data/<subject>/ses-<timestamp>/`。

## 界面风格

默认 **12×12** 网格，参照 Neuralink Webgrid 的视觉语言：

- 白色底板 + 细黑网格线，不留单元格间隙；
- **动物模式默认不显示任何文字**：无指导语、无计时、无 BPS/NTPM、无目标进度、无错误数、无图例、无提示语；
- 多键模式也不显示文字图例，目标颜色本身就是按键线索；
- 目标格为纯色块：`click_types=1` 时蓝色；`=2` 时蓝/橙；`=3` 时蓝/橙/紫；
- 蓝色 = 左键、橙色 = 右键、紫色 = 中键；目标颜色就是要求按下的键；
- 光标为黑点白描边；鼠标悬停单元格浅灰高亮，误点单元格短暂闪红；
- 倒计时只显示中央注视点 `+`；结束后为空白屏，保存路径只打印在实验者控制台。

![12×12 单键界面](docs/preview.png)

![三键模式（无文字图例）](docs/preview_multi.png)

修改默认网格：

```powershell
uv run webgrid --rows 10 --cols 10
```

## 范式流程

1. 启动后直接进入准备阶段：网格 + 中央注视点，无文字。
2. 注视点保持 `countdown_seconds` 秒（默认 2 s），随后出现第一个目标。
3. 每个试次：
   - 随机高亮一个目标格（单键模式为蓝色；多键模式按目标颜色区分所需按键），光标保留在上一帧位置；
   - 被试移动光标到目标格；
   - **click** 模式：按下与目标颜色对应的鼠标/BCI 按键；**dwell** 模式：在目标格内连续停留 `dwell_time` 秒自动选择。
4. 命中：目标短暂反馈后出现下一个目标。
5. 点错：目标保留，可继续尝试；仅用视觉反馈（光标/单元格闪红），不显示文字。
6. 超时（默认 15 s）或达到 `targets` 个目标 / `max_seconds` 后结束。
7. 结束后显示空白屏；实验者按空格或 Esc 退出，数据路径打印在控制台。

网格默认 **12×12**；`--rows/--cols` 可调。目标序列使用洗牌袋（每个格子在一个袋内出现一次），避免连续重复，同时保证空间覆盖均衡。

## 数据中的计分（界面不显示）

设：

- `N = rows × cols`：网格格子数
- `C = click_types`：点击类型数（1–3）
- `H`：命中数，`M`：误点次数，`T`：超时数
- `net = H − M`：净正确目标数

则：

```text
每目标信息量 = log2(N × C)        （bit/target）
NTPM          = net / duration_min （targets/min）
BPS           = NTPM × log2(N × C) / 60
```

这与 web-grid 的信息传输率定义一致：网格越大、点击类型越多，每个正确选择携带的信息越多；误点会从净命中数中扣除。界面不显示 BPS/NTPM，`summary.json` 仍保留这些指标，供离线分析。

示例：12×12、`click_types=1`、120 s 内 20 次命中、1 次误点：

```text
net = 19, NTPM = 9.5, bits/target = log2(144) ≈ 7.17, BPS ≈ 1.14
```

> 注意：`click_types` 同时决定“目标颜色/要求按键”和计分信息量。设为 1 时只有蓝色目标和 1 号键；设为 2 时目标为蓝/橙，必须分别按左/右键；设为 3 时增加紫色中键。按错键计一次 misclick，目标保留。

## BCI UDP 输入

```powershell
uv run webgrid --input udp --udp-port 9000
```

每个 UDP 数据报是一个 JSON 对象，建议以 60–200 Hz 持续发送：

```json
{"x": 0.12, "y": -0.30, "click": 0}
{"x": 0.16, "y": -0.25, "click": 1}
{"x": 0.16, "y": -0.25, "click": 1}
{"x": 0.18, "y": -0.20, "click": 0}
```

字段：

| 字段 | 说明 |
| --- | --- |
| `x`, `y` | 窗口归一化坐标，范围 `[-1, 1]`；原点在窗口中心，`+x` 向右，`+y` 向上。超出范围会被裁剪。 |
| `click` | 0 = 未按；1/2/3 = 按住某个键。只在 **0 → 非 0** 的跳变时产生一次选择。 |
| `event` | 可选，`"click"` 表示一次性点击事件（不需要先发 0）。 |
| `button` | 与 `event: "click"` 搭配的按键编号；缺省为 1。 |
| `select` | `true` 时为一次性点击的简写。 |

也可以发送一次性事件：

```json
{"x": 0.05, "y": 0.20, "event": "click", "button": 1}
```

- 每个数据报都必须带合法的 `x`、`y`；没有位置的事件包会被忽略。
- 启动、停止和异常处理由实验者控制；UDP 的一次点击也可以用来开始任务。
- 默认只监听 `127.0.0.1`。如解码器在另一台机器：`--udp-host 0.0.0.0`，并配置防火墙。
- 解码输出抖动较大时可加 `--smoothing 0.3`（0 = 原始，0.95 = 很平滑）。

最小发送端示例：

```python
import json
import socket
import time

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
addr = ("127.0.0.1", 9000)

while True:
    x, y = 0.0, 0.0          # TODO: 你的解码器输出
    click = 0                 # TODO: 0/1/2/3
    sock.sendto(json.dumps({"x": x, "y": y, "click": click}).encode(), addr)
    time.sleep(1 / 120)
```

按键编号约定：鼠标左键 = 1，右键 = 2，中键 = 3；BCI 端可以按自己的分类器映射到 1/2/3。

## 事件标记（EEG/BCI）

### UDP 标记

```powershell
uv run webgrid --input udp --marker-udp 127.0.0.1:9001
```

每个事件发送一个 JSON 数据报：

```json
{"code": 10, "event": "target_onset", "t": 12.345, "utc": "...", "detail": {"target_index": 3, "row": 2, "col": 5}}
```

`t` 是 PsychoPy 的单调时钟（秒），`utc` 是发送时的 UTC 时间。

### LSL 标记

```powershell
uv sync --extra lsl
uv run webgrid --input udp --lsl --lsl-stream WebGridMarkers
```

LSL 流为 `type="Markers"`、单通道 `cf_int32`、`nominal_srate=0`；适合 LabRecorder、OpenViBE、MNE-LSL 等。

### 事件码

| code | event | 说明 |
| ---: | --- | --- |
| 1 | `session_start` | 第一个目标出现前 |
| 10 | `target_onset` | 新目标实际显示（`win.flip()` 之后） |
| 20 | `hit` | 命中 |
| 30 | `misclick` | 误点（目标继续） |
| 40 | `timeout` | 当前目标超时 |
| 2 | `session_end` | 正常结束 |
| 90 | `session_abort` | Esc / 异常中止 |

目标出现标记在 `win.flip()` 返回之后发送，反应时也从该 flip 的时间戳计算。UDP 标记存在系统网络延迟；对严格 EEG 同步要求高的实验建议使用 LSL，或把标记输出扩展到并行口/采集卡。

## 数据文件

```text
data/
└── sub-01/
    └── ses-20261107-140000/
        ├── config.json    # 全部参数、Python/PsychoPy 版本、平台
        ├── events.csv     # 事件日志：session/target/click/hit/timeout...
        ├── trials.csv     # 每个目标一行（命中或超时）
        └── summary.json   # 汇总指标 + 配置快照 + 版本
```

- CSV 为 UTF-8 with BOM，方便 Excel 直接打开中文；JSON 为 UTF-8。
- `events.csv` 同时记录 `monotonic_s`（PsychoPy 时钟）与 `utc`；便于和 EEG 记录做时间对齐。
- `trials.csv` 字段包括：目标格 `target_row/target_col`、要求按键 `required_button`、`onset_s/offset_s/rt_s`、`outcome`、`misclicks`、`path_px/straight_px/path_efficiency` 等。
- `path_efficiency = 直线距离 / 实际轨迹长度`，没有移动时为空白。
- 按 Esc 中止时仍会写出已产生的数据，`summary.json` 中 `aborted` 为 `true`。
- 同一秒内重复启动会自动加 `-2`、`-3` 后缀，不覆盖已有数据。

## 常用参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--subject` | `sub-01` | 被试标签，进入目录名 |
| `--session` | 时间戳 | 会话标签 |
| `--output-dir` | `data` | 数据根目录 |
| `--rows`, `--cols` | 12, 12 | 网格尺寸（2–40，需足够分辨率） |
| `--targets` | 40 | 呈现的目标数 |
| `--max-seconds` | 300 | 时间上限；0 关闭 |
| `--selection` | `click` | `click` 或 `dwell` |
| `--dwell-time` | 1.0 | 停留选择时长（秒） |
| `--trial-timeout` | 15 | 单目标超时；0 关闭 |
| `--click-types` | 1 | 1–3；目标颜色/要求按键，同时影响计分 |
| `--feedback` | 0.35 | 命中/超时反馈时长 |
| `--countdown-seconds` | 2.0 | 倒计时总时长 |
| `--input` | `mouse` | `mouse` / `keyboard` / `udp` / `demo` |
| `--udp-host`, `--udp-port` | `127.0.0.1`, 9000 | UDP 输入地址 |
| `--smoothing` | 0 | UDP 光标指数平滑，0–0.95 |
| `--keyboard-step` | 0.035 | 键盘每次移动的归一化距离 |
| `--demo-speed` | 2.2 | autopilot 速度 |
| `--fullscreen` | 开 | 全屏（默认） |
| `--windowed` | 关 | 强制窗口模式（调试） |
| `--window-width/height` | 1280/800 | 窗口尺寸（`--windowed` 时生效） |
| `--language` | `zh` | `zh` / `en` |
| `--marker-udp` | 空 | 事件标记 UDP 地址 |
| `--lsl` | 关 | 发布 LSL 标记流（需 `--extra lsl`） |
| `--instructions` | 关 | 显示人用指导语页；动物实验保持关闭 |
| `--no-instructions` | 开 | 跳过指导语（默认） |
| `--auto-exit` | 关 | 空白结束屏 2.5 s 后自动关闭（演示/测试） |

配置文件示例见 [`configs/default.toml`](configs/default.toml)，命令行参数会覆盖文件中的同名字段：

```powershell
uv run webgrid --config configs/default.toml --input udp
```

## 键盘调试

```powershell
uv run webgrid --input keyboard
```

方向键移动光标，空格/回车选择（1 号键），数字键 `1`/`2`/`3` 分别对应左/右/中键，Esc 退出。键盘模式仅用于无鼠标环境下的调试，正式实验请使用 UDP 或鼠标。

## 测试与开发

```powershell
uv run pytest
uv run webgrid --screenshot docs/preview.png   # 视觉检查
```

项目结构：

```text
src/web_grid_paradigm/
├── cli.py               # 命令行、配置合并
├── config.py            # 参数与校验、TOML 读取
├── geometry.py          # 网格布局、像素/归一化坐标、目标洗牌袋
├── i18n.py              # 中英文 UI 文案
├── inputs.py            # UDP 光标源、autopilot（纯 Python）
├── markers.py           # UDP/LSL 事件标记
├── psychopy_runner.py   # PsychoPy 窗口、渲染、主循环
├── recorder.py          # CSV/JSON 数据写入
├── scoring.py           # BPS/NTPM 统计
└── session.py           # 试次状态机（纯 Python）
```

`geometry`、`scoring`、`session`、`inputs` 不依赖 PsychoPy，因此单元测试无需打开窗口。

## 注意事项

- **Python 版本**：项目固定为 3.11（`uv.lock` 中的解释器也是 3.11）。如果系统只有 3.12，`uv sync` 会提示安装/选择 3.11；可先 `uv python install 3.11`。
- **字体**：默认 `Microsoft YaHei`。macOS/Linux 请用 `--font` 指定系统里可显示中文的字体，或 `--language en`。
- **显示器校准提示**：首次启动可能看到 `Monitor specification not found`；这是 PsychoPy 未找到显示器校准文件，本范式使用像素坐标，不依赖该设置，可忽略。
- **全屏与缩放**：默认全屏；本地调试用 `--windowed`。正式采集建议把 Windows 显示缩放设为 100%，避免像素坐标与刷新率偏差。
- **时序**：目标出现时间取 `win.flip()` 的返回时间；请确认显示器刷新率和垂直同步。PsychoPy 的浮点渲染精度足够行为实验，但毫秒级 EEG 对齐仍建议硬件/光电校验。
- **网格密度**：格子最小 8 px；40×40 需要足够大的窗口/分辨率，否则会报“grid is too dense”。
- **数据安全**：每次事件即时 flush；程序崩溃/按 Esc 时仍保留已写入的数据，但不会补写未完成的试次。
- **范围**：本仓库不采集 EEG、不做解码、不实现 P300 行列闪烁；它是 web-grid 行为范式与 BCI 输入/标记的接口层。

## 参考

- [Neuralink Webgrid](https://neuralink.com/webgrid/)：web-grid 任务与 BPS 计分说明
- [PsychoPy 文档](https://www.psychopy.org/)
