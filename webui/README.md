# Web UI（Vue 3 + Vite + Naive UI）

控制台的 Vue 重构版本。构建产物写入 `src/web_grid_paradigm/panel/static/`，由 Python
控制台在 `/app/` 下提供（Phase 0–3）；Phase 4 会切到根路径 `/`，旧的单文件页面届时下线。

## 命令

```powershell
cd webui
pnpm install          # 首次
pnpm dev              # 开发服务器 http://127.0.0.1:5173/app/，/api 与 /events 代理到 8765
pnpm typecheck        # vue-tsc --noEmit
pnpm build            # 类型检查 + 构建 → ../src/web_grid_paradigm/panel/static/
```

开发时的典型流程：先在一个终端启动控制台，再启动前端。

```powershell
uv run webgrid --no-open-dashboard --dashboard-port 8765
cd webui; pnpm dev
# 浏览器打开 http://127.0.0.1:5173/app/
```

## 约定

- `pnpm build` 的产物**入库**（`panel/static/`），这样 `uv build` / 离线环境无需 Node。
- 只在构建期需要 Node ≥ 22 与 pnpm；运行时只依赖 Python 与浏览器。
- 目标浏览器 `chrome100+`；不引入 CDN、不下载网络字体（中文用系统字体）。
- 服务端 API 契约保持不变：`/api/state`、`/api/config`、`/events`(SSE)、
  `/api/start`、`/api/stop`、`/api/lsl`、`/api/reward/{connect,disconnect,test}`。
- 表单继续由服务端 `/api/config` 的 `schema`/`groups` 驱动（`SchemaForm.vue`，Phase 2）。
