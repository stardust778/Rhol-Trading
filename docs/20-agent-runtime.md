# 20 · Agent 运行时

> 定位：ReAct 循环、上下文压缩、系统提示词、记忆 | 规模：`agent/src/agent/` 8k 行 | 触发词：Agent、循环、压缩、提示词、记忆

## 摘要

- `AgentLoop` 是最小 ReAct：LLM → 工具 → LLM，直到没有 tool_calls
- 上下文压缩有 **4 层**，全部读 env 阈值，不要在代码里写死
- 系统提示词是**字节稳定**设计（为了 prompt cache），改动会全局失效缓存
- 记忆分两级：单次 run 的 `WorkspaceMemory`（进第一条 user 消息）和跨会话的 `PersistentMemory`（进系统提示词）
- 工具默认**懒加载**：只给模型 7 个初始工具 + `load_tools`

## 快速导航

| 我要… | 文件 | 备注 |
|---|---|---|
| 改系统提示词 | `src/agent/context.py` 的 `_SYSTEM_PROMPT` (:23-240) | 保持字节稳定 |
| 改循环行为 | `src/agent/loop.py:168` `AgentLoop` | |
| 改压缩阈值 | `src/agent/tuning.py` + env | 别改常量 |
| 改工具加载策略 | `src/agent/tool_loading.py`、`tool_loading.json` | `VIBE_TRADING_TOOL_LOADING=eager\|lazy` |
| 改技能加载 | `src/agent/skills.py` | 用户目录覆盖内置 |
| 看 trace | `src/agent/trace.py` | `trace.jsonl` |

## 详细说明

### 循环与事件

```
run() → _run_bound()
  prepare_registry（懒加载）
  → RunStateStore.save_request
  → ContextBuilder.build_messages
  → TraceWriter + run_manifest.json
  → while True:
      _compact_to_budget (四层压缩)
      TurnStream → llm.stream_chat
      ├─ tool_calls: _process_tool_calls → _batch_execute → _execute_single → ToolRegistry.execute
      └─ text: 最终内容，break
  → resolve_final_status → build_result_dict
```

事件：`text_delta, thinking_done, stream_reset, tool_call, tool_result, tool_progress, tool_heartbeat, compact, stalled, llm_usage, llm_usage_unavailable, goal.updated`

### 状态判定顺序（有语义，别调）

`stall → cancelled → budget → no_progress → content-filter → truncation → success → empty → max_iterations`

### 四层压缩

| 层 | 触发 | 代价 |
|---|---|---|
| 1 microcompact | 对话预算 80% | 零（清最老工具结果） |
| 2 context collapse | 90% | 零（折叠长文本块） |
| 3 auto compact | 超预算 | 一次 LLM 摘要调用，保留尾部 ~20K token |
| 4 `compact` 工具 | 模型主动调用 | 同 L3；已在阈值下会拒绝 |

预算来源：`VIBE_TRADING_CONTEXT_WINDOW` > 从上下文溢出错误学到的窗口 > `context_windows.json` > 128000。
总预算 `= min(window*0.8, VIBE_TRADING_CONTEXT_MAX_TOKENS=200000)`，再减去系统提示词 + 工具 schema 的静态占用。

### 记忆

| 类型 | 位置 | 注入点 |
|---|---|---|
| `WorkspaceMemory` | 单次 run 的 `run_dir` + 计数器 | **第一条 user 消息** 的 `<agent-state>` |
| `PersistentMemory` | `~/.vibe-trading/memory/` | 系统提示词的冻结快照 + `<recalled-memories>` 前 3 条 |

### 相关 env

```
VIBE_TRADING_CONTEXT_WINDOW / VIBE_TRADING_CONTEXT_MAX_TOKENS
VIBE_TRADING_TOOL_LOADING          lazy（默认）/ eager
VIBE_TRADING_TOOL_TIMEOUT_SECONDS  默认 1800
VIBE_TRADING_LLM_TIMEOUT_SECONDS
VIBE_TRADING_RUN_STALL_TIMEOUT_SECONDS
VIBE_TRADING_AGENT_MAX_ITERATIONS
VIBE_TRADING_ENABLE_SHELL_TOOLS
```

## 陷阱

1. **`TOKEN_THRESHOLD` 已废弃**：只在测试里当 monkeypatch 钩子，生产改它无效
2. **`get_env_config()` 是进程级单例**：运行时改 `os.environ` 必须 `reset_env_config()`
3. **`.env` 只加载第一个存在的**（`~/.vibe-trading/.env` > `agent/.env` > `./.env`），且不覆盖已导出的变量 —— 旧的 shell export 会赢过文件
4. 系统提示词里写死了"29 个 swarm 团队"这类数字，加东西不会自动同步
5. 压缩正确性依赖 `preserve_tool_call_ids` 和 `_fix_tool_pairs`，改压缩逻辑必须保住 tool_call/tool_result 配对

## 测试

```bash
pytest agent/tests -q -k "agent_loop or context_budget or compact or deferred_tool"
pytest agent/tests/test_agent_loop_stall_watchdog.py agent/tests/test_agent_loop_stream_retry.py -q
```
