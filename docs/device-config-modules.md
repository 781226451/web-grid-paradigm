# 设备配置模块化重构计划

> 状态：计划（未实现）
> 基线：`refactor/config-layering` @ `0ffc350`
> 目标分支：`refactor/device-config-modules`
> 范围：设备配置文件的组织、加载、校验与来源审计
> 原则：显式、互斥、可审计；不引入隐式文件，不保留文件间优先级

## 1. 现状与问题

### 1.1 现有通道

截至 `0ffc350`，配置输入有四个来源：

| 通道 | 允许的键 | 文件形态 | 备注 |
| --- | --- | --- | --- |
| `--config FILE` | 全部字段 | 平铺 / `[webgrid]` / `[reward]` | 实验、设备、启动混在一起 |
| `--lab-config FILE` | 仅设备键 | 平铺 / `[device]` / `[webgrid.device]` | 本分支新增 |
| `--reward-config FILE` / 自动 `configs/reward.toml` | 仅奖励键 | 平铺 / `[reward]` | 自动加载，且压在 `--config`、`--lab-config` 之上 |
| CLI / WebUI | 全部 / 实验+设备 | — | 已有来源记录 |

`config.json` 已落盘 `config_sources`，面板 API 已返回 `sources` / `base_sources` / `scopes` / `editable`。

### 1.2 问题

1. **文件角色重叠**：同一个设备键可以出现在 `--config`、`--lab-config`、`--reward-config` 三个文件里，谁生效取决于加载顺序。
2. **隐式加载**：`configs/reward.toml` 只要存在于当前工作目录就会被加载，显式传入的 `--config` / `--lab-config` 反而被它覆盖。
3. **模块无法独立维护**：奖励硬件、速度输入、LSL 输出无法各自成文件、各自复制到其他机器或跨实验复用。
4. **文件语法不统一**：平铺、`[webgrid]`、`[reward]`、`[device]` 多种写法，混写会静默丢键（`0ffc350` 已改为报错，但形态仍然多）。
5. **scope 只用于 UI**：`core/settings.py` 的三域划分只影响面板 `editable`，没有约束文件。

## 2. 目标与非目标

### 2.1 目标

1. 设备配置按**模块**拆成多个 TOML，可独立维护、复制、共享。
2. 每个配置键在每次运行中**只由一个显式文件设置**；文件之间不存在覆盖关系。
3. 没有隐式加载：所有文件都由命令行显式给出。
4. 文件格式统一为平铺 TOML，键名与 `ExperimentConfig` 字段一一对应。
5. 来源可追溯：逻辑来源（`device`）+ 具体文件路径都写入会话目录。
6. 迁移路径明确：旧参数、旧文件都有可执行的迁移提示。

### 2.2 非目标

- 不改变任何实验参数的语义、默认值或校验规则。
- 不把 `ExperimentConfig` 拆成嵌套对象（`config.device.joystick.port` 之类），那是后续独立重构。
- 不做 profile/manifest、环境变量、配置版本号；这些可以在本计划落地后再评估。
- 不改变 WebUI 表单字段集合（`panel/schema.py` 的 `_FORM`）。

## 3. 目标设计

### 3.1 输入通道

| 通道 | 允许的键 | 数量 | 说明 |
| --- | --- | --- | --- |
| 代码默认值 | 全部 | — | 兜底 |
| `--config FILE` | `EXPERIMENT_FIELDS \| BOOTSTRAP_FIELDS` | 1 | 实验设计 + 启动项，可提交到 git |
| `--device-config FILE` | `DEVICE_FIELDS` | 0..N，可重复 | 设备模块，本机维护 |
| CLI 参数 | 全部 | — | 覆盖文件 |
| WebUI 表单 | `EXPERIMENT_FIELDS \| DEVICE_FIELDS` | — | 仅本次运行，不写回文件 |

`input = "mouse" | "demo" | "joystick" | "lsl"` 仍然在 `--config`（实验域）；设备文件只提供参数，不决定模式。

### 3.2 优先级

```text
代码默认值
  < --config（实验 + 启动）
  < --device-config ...（设备模块；互斥，无顺序）
  < 命令行
  < WebUI（仅本次运行、仅实际改过的字段）
```

设备文件之间**没有优先级**：任意两个文件都不允许设置同一个键。因此这里的“顺序”只是书写顺序，不产生语义。

### 3.3 模块划分（建议）

按代码包切分，文件边界与维护边界一致：

| 模块文件 | 对应代码 | 键 | 数量 |
| --- | --- | --- | --- |
| `configs/velocity_input.toml` | `velocity_inputs/`（demo / joystick / lsl） | `demo_speed`、`joystick_*`、`lsl_velocity_*` | 15 |
| `configs/reward.toml` | `reward/` | `reward*` | 7 |
| `configs/lsl_outputs.toml` | `recording/lsl.py`、`recording/markers.py`、`panel/lsl_state.py` | `lsl`、`lsl_stream`、`lsl_state*` | 5 |

合计 27 个设备键，正好等于 `DEVICE_FIELDS`。

可选更细的拆法（按设备而非代码模块）：

```text
configs/joystick.toml          10 个 joystick_* 键
configs/lsl_velocity.toml       4 个 lsl_velocity_* 键
configs/demo.toml               1 个 demo_speed
configs/reward.toml             7 个 reward* 键
configs/lsl_outputs.toml        5 个 LSL 输出键
```

两种都合法；区别只是“模块”的粒度。推荐先用 3 个模块，确有独立维护需求时再拆细。

### 3.4 文件格式：平铺 + 全键名

- 只允许 `key = value`，不允许任何小节。
- 键名必须是完整字段名：`joystick.toml` 里也必须写 `joystick_port`，不能写 `port`。
- **文件名不参与语义**：加载器不根据文件名推断模块，只看键属于哪个 scope。
- 注释可以按功能分块，但注释不参与解析。

示例：

```toml
# configs/velocity_input.toml
demo_speed = 2.2

joystick_port = "COM4"
joystick_baud = 9600
joystick_address = 0
joystick_stream_mode = "periodic"
joystick_speed = 560.0
joystick_deadzone = 0.0
joystick_invert_x = false
joystick_invert_y = false
joystick_center_on_open = false
joystick_stale_after = 0.4

lsl_velocity_stream = "WebGridVelocity"
lsl_velocity_type = "Velocity"
lsl_velocity_timeout = 5.0
lsl_velocity_stale_after = 1.0
```

```toml
# configs/reward.toml
reward = "serial"
reward_policy = "per_hit"
reward_ratio = 2
reward_port = "COM3"
reward_baud = 9600
reward_amount = 1
reward_duration_ms = 50
```

```toml
# configs/lsl_outputs.toml
lsl = false
lsl_stream = "WebGridMarkers"
lsl_state = false
lsl_state_stream = "WebGridState"
lsl_state_rate = 10.0
```

### 3.5 加载与校验

加载流程：

```text
ExperimentConfig()                       # 默认值
  → --config 文件（scope: experiment+bootstrap）
  → 每个 --device-config 文件（scope: device，键互斥）
  → CLI 覆盖
  → WebUI（运行时）
  → validate()
```

校验规则（全部在启动时完成，失败返回 exit 2）：

1. `--config` 中不允许 `DEVICE_FIELDS` 的键；出现则报“该键属于设备配置，请放入 `--device-config`”。
2. 设备文件中不允许非 `DEVICE_FIELDS` 的键；出现则报“该键属于实验/启动配置，请放入 `--config`”。
3. 任意两个设备文件的键集合必须不相交；重叠时报错并列出键和两个文件。
4. 所有文件必须是平铺 TOML；出现任何 Mapping 值（`[webgrid]`、`[reward]`、`[device]` 等）都报错，并提示改用平铺键。
5. 未知键、缺失文件、非法 TOML 沿用现有错误，统一 exit 2。
6. 只有当前 `input` 模式对应的必填项做必填校验（沿用 `ExperimentConfig.validate` 的现有逻辑）。

错误示例：

```text
configs/default.toml: joystick_port is a device key; move it to --device-config
configs/joystick.toml: rows is an experiment key; move it to --config
configs/joystick.toml and configs/velocity_input.toml both set joystick_port;
keep each key in exactly one file
configs/lab.toml: [device] tables are no longer supported; use flat keys
--lab-config is deprecated; use --device-config
configs/reward.toml is no longer loaded automatically; pass
  --device-config configs/reward.toml or merge it into another device file
```

### 3.6 来源与审计

- `core/settings.py` 中 `SOURCE_LAB` / `SOURCE_REWARD` 合并为 `SOURCE_DEVICE = "device"`。
- `config.json` 保留 `config_sources`（逻辑来源），新增 `config_files`（字段 → 实际文件路径）：

```json
{
  "config_sources": {
    "rows": "config",
    "joystick_port": "device",
    "reward_port": "device",
    "dashboard_port": "cli"
  },
  "config_files": {
    "joystick_port": "configs/velocity_input.toml",
    "reward_port": "configs/reward.toml"
  }
}
```

- 面板来源徽章：`config` / `device` / `cli` / `webui`；`device` 的 tooltip 显示具体文件（`config_files`）。
- 旧 `config.json` 中的 `reward` / `lab` 值不迁移、不兼容处理；读取方只按字符串展示。

### 3.7 CLI

- `--device-config FILE`：`action="append"`，可重复，默认空列表。
- `--lab-config`：过渡期保留为 `--device-config` 的别名，追加到同一列表，并打 WARNING；一个版本后移除。
- `--reward-config`：同上，过渡期别名。
- 自动加载 `configs/reward.toml` **立即移除**；启动时如果检测到该文件且没有被任何显式设备文件（含 `--lab-config` / `--reward-config` 别名）引用，打 ERROR 并给出迁移命令（避免静默使用默认值）。
- `--config` 帮助文本改为“实验与启动配置（平铺 TOML）”。
- `--device-config` 帮助文本：`device settings (flat TOML; may be given multiple times)`。

示例：

```powershell
uv run webgrid --config configs/default.toml `
  --device-config configs/velocity_input.toml `
  --device-config configs/reward.toml `
  --device-config configs/lsl_outputs.toml
```

单文件模式仍然可用：

```powershell
uv run webgrid --config configs/default.toml --device-config configs/lab.toml
```

其中 `lab.toml` 只是“包含全部设备键的一个设备文件”，不再有特殊地位。

### 3.8 面板与 WebUI

- `/api/config`：`sources` 增加 `device`；`base_sources` 同步；可选增加 `source_files` 供 tooltip 使用。
- `/api/start`：显式校验 payload 的键都属于 `EXPERIMENT_FIELDS | DEVICE_FIELDS`，bootstrap 字段一律拒绝（当前靠表单白名单间接实现，改为显式校验）。
- 前端 `SOURCE_LABELS`：`lab` / `reward` 合并为 `device: "设备配置"`；设备字段的 tooltip 可显示文件名。
- 设备弹窗（`InputDevice`）与奖励设备连接逻辑不变；`base_config.reward_port` 仍来自最终配置。

## 4. 代码改动清单

| 文件 | 改动 |
| --- | --- |
| `src/web_grid_paradigm/core/settings.py` | 增加 `CONFIG_FILE_FIELDS`、`DEVICE_MODULES`（或删除）；`SOURCE_LAB`/`SOURCE_REWARD` → `SOURCE_DEVICE` |
| `src/web_grid_paradigm/core/config.py` | 新增 `read_config_table()`：平铺解析，拒绝 Mapping 值，拒绝未知键；`from_toml` 复用；删除 `_merge_reward_table` 与 `[webgrid]`/`[reward]` 支持 |
| `src/web_grid_paradigm/app/cli_args.py` | `load_config_resolved` 改为多设备文件；删 `apply_reward_config`、`REWARD_KEYS`、`default_reward_config`、`DEFAULT_REWARD_CONFIG`；`--device-config` 可重复；`--lab-config`/`--reward-config` 过渡别名；scope 校验与互斥检查；`sources` 记录 |
| `src/web_grid_paradigm/app/cli.py` | 传递 `sources` 不变；设备文件加载日志由加载器输出 |
| `src/web_grid_paradigm/recording/recorder.py` | `SessionRecorder` 增加 `config_files` 参数，`config.json` 新增字段 |
| `src/web_grid_paradigm/panel/state.py` | `_begin_run` 保存 `config_files`；`/api/start` scope 校验；来源标签 |
| `webui/src/stores/config.ts` | `SOURCE_LABELS` 更新；可选 `sourceFiles` |
| `configs/default.toml` | 去掉全部设备键；只保留 experiment + bootstrap |
| `configs/velocity_input.example.toml` | 新增（15 个设备键） |
| `configs/reward.example.toml` | 改为模块文件，键不变 |
| `configs/lsl_outputs.example.toml` | 新增（5 个 LSL 输出键） |
| `configs/lab.example.toml` | 删除，或保留为“全设备参考”并在 README 说明只是组合示例 |
| `tests/test_config.py` | 平铺解析、scope 分区测试 |
| `tests/test_cli.py` | 多设备文件、互斥、scope、别名、迁移错误 |
| `tests/test_reward_hardware.py` | 删除 `apply_reward_config`/自动加载相关用例，改为 `--device-config` 用例 |
| `tests/test_station.py` | 来源、`/api/start` scope |
| `tests/test_recorder.py` | `config_files` |
| `README.md`、`docs/config-parameters-upgrade.md` | 新模型、迁移、优先级 |

## 5. 实施步骤

每个步骤独立可测试、可回滚。

### Step 1：统一文件读取与 `--config` scope

- `core/settings.py` 增加 `CONFIG_FILE_FIELDS = EXPERIMENT_FIELDS | BOOTSTRAP_FIELDS`；`SOURCE_DEVICE`。
- `core/config.py` 增加 `read_config_table()`，`--config` 只接受平铺与 experiment+bootstrap 键。
- 裁剪 `configs/default.toml`（去掉设备键），更新默认值测试。
- 更新依赖 `[webgrid]` / `[reward]` 小节的 `from_toml` 用例（`test_toml_round_trip`、`test_single_config_file_can_hold_a_reward_section`、`test_nested_reward_section_under_webgrid`）。
- 测试：`--config` 含设备键报错；平铺/未知键/小节报错。
- 验收：`pytest tests/test_config.py tests/test_cli.py tests/test_reward_hardware.py` 通过。

### Step 2：多设备文件与 `--device-config`

- 增加可重复的 `--device-config`；`--lab-config` / `--reward-config` 立即变成追加别名（WARNING）。
- `load_config_resolved` 读取设备文件列表；逐文件校验 device scope；键互斥检查；记录 `sources=device` 与文件路径。
- 删除 `apply_reward_config`、`REWARD_KEYS`、`default_reward_config`、`DEFAULT_REWARD_CONFIG` 与自动加载。
- 把 `tests/test_reward_hardware.py` 中 `apply_reward_config` / 自动加载相关用例改为 `--device-config` 用例。
- 测试：单文件、多文件、重叠、非设备键、来源、缺失文件、别名。
- 验收：`pytest tests/test_cli.py tests/test_reward_hardware.py` 通过。

### Step 3：审计与面板

- `SessionRecorder` 增加 `config_files`；`SessionView` 暴露；`config.json` 写入。
- `/api/start` 显式 scope 校验；来源标签 `device`。
- 测试：`config_files`、面板 payload、bootstrap 字段拒绝。

### Step 4：示例、文档与迁移提示

- `default.toml` 已在 Step 1 裁剪；新增 `velocity_input.example.toml`、`lsl_outputs.example.toml`，改造 `reward.example.toml`，删除/改造 `lab.example.toml`。
- `configs/reward.toml` 存在但未被显式加载时 ERROR；旧 flag 的 WARNING 文案；README、升级文档、`.gitignore`。
- 测试：示例文件覆盖/互斥；迁移错误。

### Step 5：清理与全量验证

- 删除 `_lab_table` 中不再需要的分节分支、`SOURCE_LAB`/`SOURCE_REWARD`、过渡代码。
- 全量 `pytest`；如有 webui 改动，重新构建 `panel/static` 并跑 e2e。

## 6. 测试矩阵

| 用例 | 期望 |
| --- | --- |
| `--config` 平铺实验键 | 通过，source=config |
| `--config` 含设备键 | `ValueError`，提示移到 `--device-config` |
| `--config` 含小节 | `ValueError`，提示平铺 |
| 单个 `--device-config` | 通过，source=device，记录文件路径 |
| 多个 `--device-config`（键互斥） | 通过，来源正确 |
| 多个 `--device-config`（键重叠） | `ValueError`，列出键和文件 |
| 设备文件含实验/启动键 | `ValueError` |
| 设备文件含未知键 | `ValueError` |
| 设备文件含小节 | `ValueError` |
| `--lab-config` 别名 | 通过 + WARNING |
| `--reward-config` 别名 | 通过 + WARNING |
| `configs/reward.toml` 自动加载 | 不再发生；存在时 ERROR |
| 无设备文件 | 默认值，source=default |
| CLI 覆盖设备文件 | 值来自 CLI，source=cli |
| WebUI 改设备字段 | 值生效，source=webui |
| `/api/start` 传 bootstrap 字段 | 400 |
| `config.json` | 含 `config_sources` + `config_files` |
| 示例文件 | 覆盖 `DEVICE_FIELDS`、两两不相交 |
| 全量回归 | 现有 199 个用例通过 |

## 7. 迁移指南

对使用旧配置的机器：

1. `--lab-config lab.toml` → `--device-config lab.toml`（别名仍可用一个版本）。
2. `--reward-config reward.toml` → `--device-config reward.toml`（别名仍可用一个版本）。
3. 自动加载的 `configs/reward.toml`：显式加 `--device-config configs/reward.toml`，或把键并入其他设备文件后删除。
4. `--config` 里的设备键：移到对应的设备模块文件；`--config` 只保留实验 + 启动键。
5. `[webgrid]` / `[reward]` / `[device]` 小节：去掉小节，改成平铺键（`[reward] reward_port` → `reward_port`）。
6. `configs/default.toml` 里的设备键：迁到模块文件；示例仓库会同步更新。
7. `.gitignore`：忽略本机模块文件（`configs/velocity_input.toml`、`configs/reward.toml`、`configs/lsl_outputs.toml`、`configs/lab.toml`），仓库只提交 `*.example.toml` 与 `configs/default.toml`。

## 8. 风险与缓解

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 忘记传某个设备文件 | 静默回落默认值 | 启动日志列出已加载文件与键数；文档强调显式 |
| 文件间键重叠 | 行为不确定 | 加载时不相交检查，fast fail |
| 模块边界与代码漂移 | 维护混乱 | 测试断言每个 example 的键 ⊆ 模块字段、并集 = `DEVICE_FIELDS` |
| `--config` 旧文件含设备键 | 启动失败 | 明确错误 + 迁移文档；可在过渡期给 WARNING 而不是 ERROR |
| `[webgrid]` 旧语法 | 启动失败 | 过渡期 WARNING，一个版本后移除 |
| 自动 reward.toml 用户 | 参数不再生效 | 存在即 ERROR，强制显式迁移 |
| `config.json` 新增字段 | 旧读取方 | 只增不改；`config_sources` 保持原结构 |

## 9. 验收标准

1. `--config` 只接受 experiment + bootstrap 键；设备文件只接受 device 键。
2. 设备文件可重复、键互斥；重叠在启动时报错，不会被覆盖。
3. 没有隐式文件加载；`configs/reward.toml` 不再自动生效。
4. `config.json` 同时记录 `config_sources` 与 `config_files`。
5. 三个模块示例文件的键集合两两不相交，并集等于 `DEVICE_FIELDS`。
6. `--lab-config`/`--reward-config` 至少有一个版本的迁移别名与 WARNING。
7. 全量测试通过；README 与升级文档同步。
8. 旧配置的每一步迁移都有可执行的错误提示。

## 10. 待确认

1. **模块粒度**：默认 3 个模块（velocity_input / reward / lsl_outputs），还是 6 个（再拆 joystick / lsl_velocity / demo）？
2. **`--config` 的 `[webgrid]` 兼容**：直接报错，还是保留一个版本的 WARNING？
3. **来源命名**：统一 `device`，还是保留 `lab` 作为别名值？
4. **profile/manifest**：命令行过长时是否现在就加，还是先接受多参数？
