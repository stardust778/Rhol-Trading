# 50 · API / 前端 / 渠道

> 定位：FastAPI 装配、鉴权、SSE、React 页面、IM 桥 | 规模：`src/api/` 12.4k + `frontend/` 45k | 触发词：改 UI、加路由、SSE、鉴权、Telegram

## 摘要

- `api_server.py` 只是装配器：20 个 `register_*_routes(app)`，**没有 APIRouter、没有 prefix**
- 设了 `API_AUTH_KEY` 后，**所有**调用都要 Bearer，连 loopback 和 `/docs` 也不例外
- SSE 用一次性 ticket（60 秒、单次），避免把长期 key 放进 query
- SSE ticket 和事件环形缓冲都是**进程内**的 → `--workers > 1` 会直接坏掉
- 前端单一 Zustand store + 一个 2362 行的 `api.ts` 客户端

## 快速导航

| 我要… | 位置 |
|---|---|
| 加一个路由 | `src/api/<名字>_routes.py` + `api_server.py` 里 `register_` |
| 看鉴权 | `src/api/security.py` |
| 看聊天接口 | `src/api/sessions_routes.py` |
| 看 run 详情 | `src/api/runs_routes.py`、`run_artifacts.py` |
| 看前端路由 | `frontend/src/router.tsx` |
| 看流式实现 | `frontend/src/hooks/useSSE.ts`、`pages/Agent.tsx` |
| 加 IM 渠道 | `src/channels/<名字>.py`（`BaseChannel` 子类） |

## 详细说明

### 接口（做自己的 UI 只用这三条）

```
POST /sessions                      → 建会话
POST /sessions/{id}/messages        → 发消息
GET  /sessions/{id}/events          → SSE 事件流
GET  /runs/{id}/preview             → run 卡片（轻）
GET  /runs/{id}                     → run 详情（重）
```

事件类型：`text_delta` `thinking_done` `tool_call` `tool_result` `tool_progress` `tool_heartbeat` `compact` `stalled` `llm_usage` `attempt.*` 等约 35 种。

### 鉴权

- `API_AUTH_KEY`（别名 `VIBE_TRADING_API_KEY`）一设，全部请求要 `Authorization: Bearer`
- 没设 key 时才信任 loopback
- 非 GET 检查 `Sec-Fetch-Site` / `Origin`（反 CSRF）
- Host 必须命中白名单（防 DNS rebinding）
- `/auth/sse-ticket` 签发一次性 ticket，`require_event_stream_auth` 接受 bearer 或 `?ticket=`

### 路由分组

`/sessions` `/runs` `/settings/*` `/live/*` `/mandate/commit` `/api/portfolio/*` `/api/paper-accounts/*` `/swarm/*` `/scheduled-runs` `/channels/*` `/alpha/*` `/options/*` `/api/research-lab/*` `/api/research-artifacts/*` `/upload` `/live` `/health`

### 前端

16 个页面，全部懒加载：`/agent` `/about` `/reports` `/runs/:id` `/compare` `/correlation` `/alpha-zoo` `/research-lab` `/research-artifacts` `/options` `/paper-trading` `/portfolio` `/pixel-office` `/scheduled` `/runtime` `/settings`

状态：`stores/agent.ts`（单一 Zustand，含 per-session LRU 缓存）。
HTTP：`lib/api.ts` 唯一出口，`BASE = ""`（同源，开发靠 Vite proxy）。
流式：`useSSE` 包 `EventSource`，指数退避 1s→30s，`Last-Event-ID` 续传，500 条事件去重；`Agent.tsx` 用 `requestAnimationFrame` 合并刷新。

### 渠道

`BaseChannel` 抽象（`start/stop/send` + 可选流式方法），`registry.py` 用 `pkgutil` 自动发现 16 个适配器，也支持外部插件（entry point `vibe_trading.channels`）。
配置在 `~/.vibe-trading/agent.json` 的 `channels.<name>`（`extra="allow"`），Web 表单从 `default_config()` 自动生成。
配对：`allow_from: ["*"]` > 显式白名单 > 配对码（8 位、600 秒）；`/pairing` 只接受 operators。

## 陷阱

1. **两个 `serve` 默认值不一致**：`cli/_legacy.py` 声明 `--host 0.0.0.0`，但实际只转发 `raw_argv`，最终 `server_cli.py` 的默认 `127.0.0.1:8000` 生效
2. **Vite 端口是 5899，但 `--dev` 打印 5173**
3. **CORS 默认不含 8899/5899** —— 靠同源 proxy 才能工作
4. **路由前缀不统一**：`/api/portfolio` 有前缀，`/runs` 没有
5. **新增 SPA 页面若与 API 路径冲突**，要同时改 `api/helpers.py` 的 `_SPA_HTML_*` 和 `vite.config.ts` 的 proxy 白名单（还要改 `viteProxy.test.ts`）
6. 前端把 API key 存在 `localStorage`（XSS 可读），只靠严格 CSP 缓解
7. 加 `API_AUTH_KEY` 后 `/docs` 返回 **404** 是故意的

## 测试

```bash
pytest agent/tests/test_api_infrastructure.py agent/tests/test_security_auth_api.py -q
pytest agent/tests/test_session_events.py agent/tests/api -q
cd frontend && npm run test:run
```
