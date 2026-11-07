# Web UI（Vue 3 + Vite + Naive UI）

控制台的 Vue 重构版本。构建产物写入 `src/web_grid_paradigm/panel/static/`，由 Python
控制台在根路径 `/` 提供；旧的单文件页面（`panel/dashboard.html`）已在收尾时删除。

## 进度

- **Phase 0（已完成）**：Vite + Vue + Naive UI 脚手架、静态路由、类型化 API 封装。
- **Phase 1（已完成）**：只读监控——网格 canvas（目标/光标/dwell 进度/误点闪红）、
  进度条、KPI、反应时图、Block 结果、最近 trial、日志；数据全部来自 `/events` 的 SSE 增量。
- **Phase 2（已完成）**：`SchemaForm` 按 `/api/config` 的 `schema/groups` 渲染全部 34 个字段
  （text / int / float / bool / choice），启动/中止按钮，运行中锁定参数，服务端 400 错误显示在表单顶部。
- **Phase 3（已完成）**：奖励设备区（连接…弹窗填串口/波特率、断开、测试一次、按交付方式显示状态）
  与 LSL 状态流卡（启停、推送计数）。
- **Phase 4（已完成）**：Playwright E2E（Edge，5 条：外壳/表单/监控卡/启动到完成/校验错误）、
  窄屏（≤1000px 单列、表单不再内部滚动）、`test:e2e` 脚本。
- **收尾（已完成）**：历史运行表（补齐旧页最后一个区块）、vendor 拆包（应用 chunk 23.6 KB，
  `naive-ui` 单独缓存）。
- 旧单文件页面与 `/legacy` 路由已删除，Git 历史里仍可找回。

## 命令

```powershell
cd webui
pnpm install          # 首次
pnpm dev              # 开发服务器 http://127.0.0.1:5173/，/api 与 /events 代理到 8765
pnpm typecheck        # vue-tsc --noEmit
pnpm build            # 类型检查 + 构建 → ../src/web_grid_paradigm/panel/static/
```

开发时的典型流程：先在一个终端启动控制台，再启动前端。

```powershell
uv run webgrid --no-open-dashboard --dashboard-port 8765
cd webui; pnpm dev
# 浏览器打开 http://127.0.0.1:5173/
```

## 约定

- `pnpm build` 的产物**入库**（`panel/static/`），这样 `uv build` / 离线环境无需 Node。
- 只在构建期需要 Node ≥ 22 与 pnpm；运行时只依赖 Python 与浏览器。
- 目标浏览器 `chrome100+`；不引入 CDN、不下载网络字体（中文用系统字体）。
- 服务端 API 契约保持不变：`/api/state`、`/api/config`、`/events`(SSE)、
  `/api/start`、`/api/stop`、`/api/lsl`、`/api/reward/{connect,disconnect,test}`。
- 表单继续由服务端 `/api/config` 的 `schema`/`groups` 驱动（`SchemaForm.vue`）。
- 当前 block 的 BPS 由前端计算（`lib/metrics.ts`，与 `scoring.py` 同公式），
  `useBlockMetrics()` 提供实时值；SSE 里的 `block_bps` 保留用于对照。
- BPS 采用 Eqn. 2（Shenoy, Willett, Nuyujukian & Henderson, *Performance Considerations
  for General-Purpose Typing BCIs, Including the Handwriting BCI*, Stanford Tech. Report #01, 2021）：
  `log2(N) × max(命中 − 误点, 0) ÷ block 秒数`（无 delete 键，因此不减去 1）；误点多于命中时按
  `max(…, 0)` 记为 0，`ntpm` 仍保留负值（`bps.spec.ts` 覆盖截断行为）。
- 端到端测试会自己启动控制台（`playwright.config.ts` 的 `webServer`），使用系统安装的 Edge
  （`channel: "msedge"`），不需要下载浏览器：

  ```powershell
  pnpm test:e2e        # 5 条，约 10 s；第一次会等 webgrid 启动
  ```
