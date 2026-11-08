# 配置与传参升级方案

> 状态：草案  
> 范围：实验参数、设备参数、启动参数、CLI、TOML、WebUI、配置落盘与审计  
> 原则：本文件只描述方案，不包含代码修改

## 1. 背景

当前程序有三类参数入口：

1. 命令行参数，例如 `--rows 8 --input joystick`；
2. TOML 配置文件，例如 `--config configs/default.toml`；
3. WebUI 表单，在控制台页面修改后点“启动实验”。

当前实际合并顺序大致是：

```text
代码默认值
  < --config TOML
  < configs/reward.toml / --reward-config
  < 命令行参数
  → base_config
  → WebUI 表单值覆盖 base_config
  → validate
  → 启动
```

当前代码中有：

- `ExperimentConfig` 58 个字段；
- `panel/schema.py` 45 个 WebUI 字段，其中 30 个内联字段；
- 13 个字段不在 WebUI 表单中，而是从 `base_config` 继承，或由独立 UI 控制；
- `--run-now` 直接使用 CLI/文件配置启动，不经过 WebUI 表单；
- `configs/default.toml` 与 `ExperimentConfig` 默认值目前一致。

相关代码：

- [core/config.py](../src/web_grid_paradigm/core/config.py)
- [app/cli_args.py](../src/web_grid_paradigm/app/cli_args.py)
- [panel/schema.py](../src/web_grid_paradigm/panel/schema.py)
- [panel/state.py](../src/web_grid_paradigm/panel/state.py)
- [configs/default.toml](../configs/default.toml)
- [configs/reward.example.toml](../configs/reward.example.toml)

## 2. 当前问题

| 问题 | 影响 |
| --- | --- |
| 所有字段走同一条全局优先级链 | Bootstrap、实验设计、设备参数混在一起，难以解释 |
| WebUI 只覆盖 45 个字段 | 另外 13 个字段只能继承，用户看不到也无法修改 |
| WebUI 与 CLI 的优先级没有显式文档 | “为什么页面还是旧值”或“为什么 CLI 被覆盖”难以判断 |
| WebUI 修改仅当前进程有效 | 重启后丢失，无法保存常用配置 |
| `--run-now` 与面板模式语义不清 | 启动后页面仍可编辑/启动，容易误操作 |
| 字段描述有三套 | dataclass、argparse 映射、panel schema 容易漂移 |
| reward TOML 隐式叠加 | `--config` 与 `configs/reward.toml` 同时设置硬件时优先级不直观 |
| 没有 source 元数据 | 无法追溯某个值来自默认值、文件、CLI 还是 WebUI |
| 没有配置版本 | 格式演进后只能靠 unknown key 报错 |

## 3. 设计目标

### 目标

1. 每个参数有明确的 **配置域** 和 **来源优先级**；
2. WebUI 只编辑适合在页面上修改的字段；
3. `--run-now` 是可复现的命令行运行模式，不依赖 WebUI；
4. 最终生效配置可以保存、导出、追溯来源；
5. CLI、WebUI、TOML 使用同一套字段定义和校验规则；
6. WebUI 不自动改写仓库中的配置文件。

### 非目标

- 不引入远程配置中心；
- 不引入数据库配置；
- 不改变实验参数本身的物理含义；
- 不在此方案中恢复已删除的 UDP/keyboard 输入兼容；
- 不把 WebUI 做成多人并发编辑系统。

## 4. 核心设计：配置分域

建议把配置拆成三个域，而不是让 58 个字段共享一个优先级链。

| 域 | 典型字段 | 建议来源 | WebUI |
| --- | --- | --- | --- |
| Bootstrap / 启动域 | `dashboard_host`、`dashboard_port`、`dashboard_open`、日志、debug | 默认值、环境变量、CLI | 只读，启动后不可编辑 |
| Experiment / 实验域 | `subject`、`session`、`output_dir`、`blocks`、`targets`、`rows`、`cols`、`selection`、`dwell_time`、`input` | 默认值、实验 TOML、CLI，最后 WebUI | 可编辑 |
| Device / 设备域 | `joystick_port/baud`、`lsl_velocity_stream/type`、`reward_port/baud`、LSL 标记流 | 默认值、本机 lab TOML、CLI，最后 WebUI 设备弹窗 | 可编辑，通过设备弹窗 |

### 4.1 字段归属建议

- **Bootstrap**
  - `dashboard`
  - `dashboard_host`
  - `dashboard_port`
  - `dashboard_open`
  - 日志级别、日志文件等未来启动项

- **Experiment**
  - `subject`
  - `session`
  - `output_dir`
  - `language`
  - `font`
  - `rows`
  - `cols`
  - `blocks`
  - `targets`
  - `block_rest`
  - `max_seconds`
  - `selection`
  - `dwell_time`
  - `trial_timeout`
  - `click_types`
  - `feedback`
  - `iti`
  - `countdown_seconds`
  - `seed`
  - `input`
  - `fullscreen`
  - `window_width`
  - `window_height`
  - `screen`
  - `hide_cursor`
  - `skip_instructions`
  - `auto_exit`

- **Device**
  - `demo_speed`（输入行为，可归 Experiment 或 Device）
  - `joystick_port`
  - `joystick_baud`
  - `joystick_address`
  - `joystick_stream_mode`
  - `joystick_speed`
  - `joystick_deadzone`
  - `joystick_invert_x`
  - `joystick_invert_y`
  - `joystick_center_on_open`
  - `joystick_stale_after`
  - `lsl_velocity_stream`
  - `lsl_velocity_type`
  - `lsl_velocity_timeout`
  - `lsl_velocity_stale_after`
  - `lsl`
  - `lsl_stream`
  - `lsl_state`
  - `lsl_state_stream`
  - `lsl_state_rate`
  - `reward`
  - `reward_policy`
  - `reward_ratio`
  - `reward_port`
  - `reward_baud`
  - `reward_amount`
  - `reward_duration_ms`

字段归属不必和现有 dataclass 一一对应；实施时可以保留 `ExperimentConfig` 作为“最终解析结果”，另外增加启动/设备配置对象。

## 5. 优先级设计

### 5.1 Bootstrap

```text
默认值 < 环境变量 < 命令行
```

理由：

- `dashboard_host`、`dashboard_port` 启动后不能再改；
- WebUI 不应出现“改了但必须重启”的字段；
- 环境变量适合机器/容器部署。

建议环境变量：

```text
WEBGRID_DASHBOARD_HOST
WEBGRID_DASHBOARD_PORT
WEBGRID_LOG_LEVEL
```

环境变量只用于启动参数，不用于实验设计参数。

### 5.2 Experiment

```text
默认值
  < experiment.toml
  < 命令行参数
  < WebUI 当前会话值
```

说明：

- CLI 是启动时的预填值；
- WebUI 是实验者在页面上的显式修改，应最后生效；
- 如果希望 CLI 强制锁定，使用 `--run-now`，或后续增加 `--lock`；
- WebUI 修改只对当前会话有效，不自动写入仓库文件。

### 5.3 Device

```text
默认值
  < lab.toml（机器本地设备配置）
  < 命令行参数
  < WebUI 设备弹窗
```

说明：

- 设备配置是“这台机器”的属性，不应写进每个人的实验设计文件；
- WebUI 设备弹窗的修改对当前会话/后续运行生效，是否保存到 lab 配置由用户显式选择；
- `reward_port`、`joystick_port` 等不应在实验 TOML 中反复复制。

### 5.4 `--run-now`

建议定义为：

```text
默认值 < experiment.toml < lab.toml < 命令行
```

不读取 WebUI 表单。

同时建议：

- `--run-now` 启动的面板为只读监控模式；
- 参数表单隐藏或禁用“启动实验”按钮；
- 日志和有效配置文件中记录 `source=mode=run-now`；
- 如需再次用页面调参，另起一个正常的 `uv run webgrid`。

### 5.5 优先级总表

| 来源 | Bootstrap | Experiment | Device | `--run-now` |
| --- | --- | --- | --- | --- |
| 代码默认值 | ✓ | ✓ | ✓ | ✓ |
| `experiment.toml` | - | ✓ | 可选 | ✓ |
| `lab.toml` | 可选 | - | ✓ | ✓ |
| 环境变量 | ✓ | - | - | ✓ |
| CLI | ✓ | ✓ | ✓ | ✓ |
| WebUI 会话 | ✗ | ✓ | ✓ | ✗ |

`✓` 表示参与该域，`✗` 表示不允许。

## 6. 文件与命令设计

### 6.1 推荐目录

```text
configs/
├── experiment.toml          # 实验设计，可提交到仓库
├── experiment.example.toml
├── lab.toml                 # 本机设备配置，建议 gitignore
├── lab.example.toml
└── profiles/                # 可选，用户保存的实验配置
```

如果暂时不拆两个文件，至少应明确两个逻辑小节：

```toml
[experiment]
rows = 12
cols = 12

[device]
joystick_port = "COM4"
reward_port = "COM3"

[bootstrap]
dashboard_host = "127.0.0.1"
dashboard_port = 8765
```

但这需要加载器支持分域，不能只靠平铺 key。

### 6.2 启动命令

```powershell
# 正常：启动面板，WebUI 可以覆盖实验参数
uv run webgrid `
  --config configs/experiment.toml `
  --lab-config configs/lab.toml

# 可复现：不经过 WebUI，按 CLI/文件直接运行
uv run webgrid `
  --config configs/experiment.toml `
  --lab-config configs/lab.toml `
  --run-now

# 完全无面板
uv run webgrid --no-dashboard --config configs/experiment.toml
```

### 6.3 文件职责

- `experiment.toml`：被试默认值、网格、任务、block/trial、选择方式、输入方式；
- `lab.toml`：串口、LSL 流、奖励硬件、标记硬件；
- `bootstrap`：控制台地址、日志、debug 等启动项；
- `profiles/*.toml`：用户从 WebUI 保存的实验配置，不进入 git。

### 6.4 不推荐的隐式规则

- 不再同时自动加载 `configs/reward.toml` 并与 `--config` 中的硬件字段竞争；
- 不在 WebUI 保存时自动改写 `configs/experiment.toml`；
- 不在 `--config` 中同时承载实验、设备、启动三类配置而不加区分。

## 7. 合并、校验与审计

### 7.1 统一合并流程

```text
读取各层原始值
  → 记录每个值的 source
  → 按域合并
  → 转换为 ExperimentConfig / BootstrapConfig / DeviceConfig
  → 一次性 validate
  → 生成 effective config
  → 启动
```

要求：

- 每层只覆盖自己的域；
- 合并过程中不做隐式类型转换；
- 校验只做一次，错误信息带字段名和来源；
- 失败时不启动、不写半成品配置。

### 7.2 有效配置落盘

建议在会话目录的 `config.json` 或新增 `config_effective.json` 中保存：

```json
{
  "config_version": 1,
  "mode": "webui",
  "values": {
    "rows": 10,
    "subject": "sub-01",
    "joystick_port": "COM4"
  },
  "sources": {
    "rows": "webui",
    "subject": "experiment.toml",
    "joystick_port": "lab.toml",
    "dashboard_port": "cli"
  }
}
```

用途：

- 复现实验；
- 排查“为什么这个值是 10”；
- 对比两次运行的参数差异。

### 7.3 配置版本

建议增加：

```toml
config_version = 1
```

规则：

- 未知版本直接报错；
- 未知 key 直接报错；
- 不做隐式迁移；
- 如需迁移，提供显式命令或脚本，不在加载时静默改写。

## 8. WebUI 与 API 设计

### 8.1 `/api/config` 返回内容

建议从：

```json
{
  "schema": [],
  "groups": [],
  "values": {},
  "control": true
}
```

扩展为：

```json
{
  "schema": [],
  "groups": [],
  "values": {},
  "sources": {
    "rows": "experiment.toml",
    "joystick_port": "lab.toml",
    "dashboard_port": "cli"
  },
  "editable": {
    "rows": true,
    "dashboard_port": false
  },
  "scopes": {
    "rows": "experiment",
    "dashboard_port": "bootstrap"
  },
  "control": true
}
```

### 8.2 `/api/start` 约束

- 只接受 `editable=true` 的字段；
- 不接受 `dashboard*` 等 Bootstrap 字段；
- 服务端再次执行域合并和校验，不能信任前端；
- 启动成功后返回 effective config 摘要和来源。

### 8.3 WebUI 行为

- Bootstrap 字段显示为只读；
- Experiment/Device 字段显示来源标签：

```text
rows = 10      [WebUI]
subject = sub-01 [experiment.toml]
COM4           [lab.toml]
```

- 增加“重置为启动配置”；
- 增加“另存为 profile”，写入用户配置目录，不写仓库；
- 增加“导出有效配置”；
- `--run-now` 模式下面板只读。

### 8.4 用户配置文件位置

建议使用跨平台用户目录，而不是仓库：

```text
Windows: %APPDATA%\webgrid\profiles\*.toml
macOS:   ~/Library/Application Support/webgrid/profiles/*.toml
Linux:   ~/.config/webgrid/profiles/*.toml
```

## 9. 单一字段规范

当前字段信息分散在：

- `ExperimentConfig` 的 dataclass 字段；
- `app/cli_args.py` 的 argparse 映射；
- `panel/schema.py` 的 `_FORM`；
- README 的参数表；
- 默认 TOML。

建议定义一个统一的字段规范，例如：

```python
FieldSpec(
    name="rows",
    scope="experiment",
    type="int",
    default=12,
    min=2,
    max=40,
    web_editable=True,
    cli=True,
    group="实验设计",
    label="Grid 行数",
)
```

字段规范至少包含：

- `name`
- `scope`：bootstrap / experiment / device
- `type`：text / int / float / bool / choice
- `default`
- `min` / `max` / `choices`
- `web_editable`
- `cli`
- `group`
- `label`
- `dialog`（设备弹窗归属）
- `persist`（是否允许保存到 profile）

然后：

- 从同一份规范生成/校验 CLI parser；
- 生成 WebUI schema；
- 生成默认 TOML；
- 生成 README 参数表；
- 在测试中检查字段集合一致性。

这样可以避免再次出现“代码有字段、表单没有、文档漏了”的漂移。

## 10. 迁移步骤

### Phase 0：基线与决策

- 记录当前字段、TOML、CLI、schema 的字段集合；
- 确认三个域的字段归属；
- 确认 WebUI 是否高于 CLI；
- 确认 `--run-now` 是否改为只读监控；
- 确认是否保留 `configs/reward.toml` 的兼容加载。

### Phase 1：来源元数据与审计

- 在加载器中引入 `source` 记录；
- `/api/config` 返回 `sources`、`editable`、`scopes`；
- 保存 effective config；
- 此阶段不改变优先级，只增加可观测性。

### Phase 2：配置分域与文件拆分

- 引入 `experiment.toml` / `lab.toml` 两个逻辑层；
- 逐步把 reward 配置并入 lab 配置；
- 明确 Bootstrap 字段只能来自 CLI/环境变量；
- 保持最终 `ExperimentConfig` 兼容。

### Phase 3：WebUI 行为调整

- Bootstrap 字段只读；
- 显示来源；
- 增加重置、另存为 profile、导出有效配置；
- `--run-now` 表单只读。

### Phase 4：单一字段规范

- 用字段规范生成或校验 CLI/UI；
- 删除重复的字段映射；
- 增加字段集合一致性测试。

### Phase 5：清理与文档

- 更新 README 的参数、配置文件、优先级说明；
- 更新示例 TOML；
- 删除旧入口说明；
- 增加迁移说明。

## 11. 测试计划

### 单元测试

- 三个域各自的优先级矩阵；
- WebUI 覆盖 CLI、CLI 覆盖文件的场景；
- `--run-now` 不使用 WebUI；
- Bootstrap 字段拒绝 WebUI 修改；
- source 记录正确；
- effective config 内容正确；
- 未知配置版本/未知 key 报错；
- 字段集合一致性。

### API 测试

- `/api/config` 返回 sources/editable/scopes；
- `/api/start` 拒绝 Bootstrap 字段；
- `/api/start` 合并后使用 WebUI 值；
- 校验失败返回字段级错误。

### E2E

- 页面显示来源标签；
- 重置恢复启动配置；
- 保存 profile 不修改仓库文件；
- 导出 effective config；
- `--run-now` 模式表单只读。

## 12. 验收标准

1. 每个配置字段都能回答：
   - 属于哪个域？
   - 默认值是什么？
   - 当前值来自哪里？
   - WebUI 是否可编辑？
2. 同一份输入在 CLI 和 WebUI 下得到可解释的最终配置；
3. 最终配置和来源写入会话目录；
4. WebUI 不能修改 Bootstrap 字段；
5. `--run-now` 不依赖 WebUI，且可复现；
6. `experiment.toml` 和 `lab.toml` 的职责清晰；
7. CLI、TOML、schema、README 的字段集合一致；
8. WebUI 保存 profile 不写入 git 工作区；
9. 所有现有测试通过。

## 13. 风险与待决策

| 风险/决策 | 说明 | 建议 |
| --- | --- | --- |
| WebUI 高于 CLI | 可能让 CLI 的“强制值”失效 | 默认采用；需要锁定时增加 `--lock` |
| `--run-now` 只读 | 改变现有交互 | 明确文档；正常调参用普通模式 |
| 拆分两个 TOML | 增加文件数量 | 先逻辑分域，再物理拆分 |
| 旧 reward 配置兼容 | 可能与新 lab 配置冲突 | 只保留一种加载路径，或提供显式迁移 |
| profile 存储位置 | Windows/macOS/Linux 不同 | 使用用户配置目录，不写仓库 |
| 多浏览器并发 | 后写覆盖前写 | 当前单操作者场景可接受；未来加 revision |
| 配置版本 | 旧文件可能无版本 | 无版本按 v0 处理并报明确错误，或要求显式迁移 |

## 14. 推荐的最小落地版本

如果不想一次改太多，可以先做：

1. 在文档和代码中明确三个域；
2. `/api/config` 返回 `sources` 和 `editable`；
3. Bootstrap 字段从 WebUI 表单移除或只读；
4. `--run-now` 启动的面板改为只读监控；
5. WebUI 增加“重置为启动配置”；
6. 最终配置保存 `sources`。

这六项不需要拆分配置对象，也能显著降低“参数到底从哪来”的困惑。

之后再考虑：

- `experiment.toml` / `lab.toml` 物理拆分；
- 统一字段规范；
- 用户 profile；
- 环境变量；
- 配置版本。
