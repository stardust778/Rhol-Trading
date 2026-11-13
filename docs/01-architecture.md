# 01 · 总体架构

> 定位：两条主链（对话 / 回测）如何交接 | 阅读时长 3 分钟

## 摘要

- 系统有**两条独立但共享磁盘的链**：Agent 对话链产出 `run_dir`，回测链消费 `run_dir`
- Agent 的核心是 `AgentLoop`（ReAct）+ `ToolRegistry`（135 个工具定义）
- 工具是唯一的副作用入口；回测工具是个薄壳，真正干活的是**子进程** `python -m backtest.runner`
- 所有跨链数据都通过 `~/.vibe-trading/runs/<run_id>/` 交换，没有内存共享

## 链一：一次对话

```
CLI  cli/main.py:main → _interactive_loop → cli/_legacy.py:_run_agent
API  src/api/sessions_routes → SessionService.send_message → _run_attempt → _run_with_agent
MCP  mcp_server.py:main → FastMCP 工具函数（直接调工具，不走 ReAct）
                          ↓
            ChatLLM + build_registry() + AgentLoop(...)
                          ↓
  AgentLoop.run
    → prepare_registry（懒加载：默认只给模型 7 个工具）
    → ContextBuilder.build_messages（系统提示词 + 记忆 + 技能摘要）
    → 循环：
        四层压缩 → TurnStream → llm.stream_chat
        → 有 tool_calls：_batch_execute（只读并行 / 写串行）
             → ToolRegistry.execute → BaseTool.execute() → JSON 字符串
        → 无 tool_calls：输出最终文本，退出循环
    → build_result_dict → trace.close
```

**关键类**

| 类 | 位置 |
|---|---|
| `AgentLoop` | `agent/src/agent/loop.py:168` |
| `ContextBuilder` | `agent/src/agent/context.py:250` |
| `ChatLLM` | `agent/src/providers/chat.py:339` |
| `ToolRegistry` / `BaseTool` | `agent/src/agent/tools.py:70` / `:13` |
| `SessionService` | `agent/src/session/service.py:77` |
| `RunStateStore` | `agent/src/core/state.py` |

## 链二：一次回测

```
backtest 工具（src/tools/backtest_tool.py:193）
  → safe_run_dir 校验
  → 子进程：python -m backtest.runner <run_dir>
        config.json + code/signal_engine.py
        → BacktestConfigSchema 校验
        → AST 扫描 signal_engine（禁危险 import / 顶层副作用）
        → 数据加载（source=auto → 市场识别 → 降级链）
        → BaseEngine.run_backtest：逐 bar 撮合
        → metrics / run_card / artifacts/*
  → RunStateStore.mark_success / mark_failure（写 state.json）
```

**要点**：回测跑在子进程里，所以工具超时（`VIBE_TRADING_TOOL_TIMEOUT_SECONDS`，默认 1800s）到点会杀掉并标记失败，但会保留部分产物。

## 两条链的交接点：`run_dir`

```
~/.vibe-trading/runs/<YYYYmmdd_HHMMSS_ff>_<hex6>/
├── req.json  state.json  run_card.json  config.json
├── code/signal_engine.py
├── logs/runner_stdout.txt  runner_stderr.txt
└── artifacts/
    ├── ohlcv_<code>.csv  equity.csv  positions.csv  target_positions.csv
    ├── trades.csv  fills.jsonl  metrics.csv
    └── risk_xray.*  rebalance_notes.*  validation.json
```

**每轮对话都会建一个 run 目录**，包括纯文本回复 → `GET /runs` 大部分是噪音，用 `preview.report_worthy` 过滤。

## 运行时目录

```
~/.vibe-trading/            # 或 $VIBE_TRADING_HOME
├── .env                    # 优先于 agent/.env 加载
├── agent.json              # MCP servers / channels
├── sessions/<id>/          # session.json, messages.jsonl, trace.jsonl, attempts/
├── runs/<run_id>/          # 见上
├── memory/  skills/user/   # 跨会话记忆 / 用户技能（覆盖内置）
├── strategy_store.db       # 策略库
├── strategy_discovery.db   # 市场状态证据
├── hypotheses.json
├── live/                   # mandate.json, HALT, audit*.jsonl（当前不用）
└── cache/loaders/          # 行情缓存（默认关）
```

## 陷阱

- 对话链和回测链**不共享内存**：Agent 只能通过文件系统看回测结果
- `api_server.py` 是个 re-export 兼容层，几百个测试符号挂在它上面，改动风险高
- 工具是唯一副作用入口；想在 Agent 里加新能力 = 加工具，不是加脚本
