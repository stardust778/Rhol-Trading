# AGENTS.md

本文件是本地 agent 上下文入口（已在 `.gitignore` 中，不会提交）。

## 第一步

读 [docs/README.md](docs/README.md)（67 行索引），然后**只读**当前任务相关的 1 篇：

| 任务 | 文档 |
|---|---|
| 写/改策略 | [docs/13-strategy-authoring.md](docs/13-strategy-authoring.md) |
| 弄懂回测/指标 | [docs/10-backtest.md](docs/10-backtest.md) |
| 数据拉不到/复权 | [docs/11-data-sources.md](docs/11-data-sources.md) |
| 加因子 | [docs/12-factors.md](docs/12-factors.md) |
| 改 Agent/工具 | [docs/20-agent-runtime.md](docs/20-agent-runtime.md)、[docs/21-tools.md](docs/21-tools.md) |
| A 股日常 | [docs/60-a-share-playbook.md](docs/60-a-share-playbook.md) |
| 踩坑 | [docs/90-gotchas.md](docs/90-gotchas.md) |

## 硬规则（会静默出错）

1. 信号在 bar `t` 收盘算，引擎在 `t+1` 开盘成交 —— **策略里不要再 shift**
2. `position_adjustment` 默认 `hold`，会吞调仓；写配置时显式声明
3. 新增工具：`is_readonly` 默认 True、`repeatable` 默认 False，写工具必须显式改
4. 新增市场引擎要改三处（engine / runner 路由 / `_MARKET_PATTERNS`），漏一处会静默用错规则
5. A 股代码必须带后缀（`.SH` / `.SZ` / `.BJ`）
6. 收益率是小数；年化基期 252/365/260 不可混

## 环境

```bash
cd /Users/lirihao/Vibe-Trading && source .venv/bin/activate
python -m pytest agent/tests/test_base_engine.py -q      # 冒烟（1 秒，104 passed）
python -m pytest --ignore=agent/tests/e2e_backtest --ignore=agent/tests/test_e2e_harness_v2.py -q
# LLM 已配置为 deepseek-v4-flash，只差 ~/.vibe-trading/.env 里的 DEEPSEEK_API_KEY
vibe-trading                                             # CLI/TUI
vibe-trading serve --port 8899                           # Web（dist 已构建）
```

- Python 3.12.16（Homebrew）+ 项目内 `.venv`；pip 走清华镜像
- Node 22.23.5 在 `/opt/homebrew/opt/node@22/bin`，但 shell 的 PATH 固定了 Node 18 → 前端命令要显式加 PATH
- **Yahoo/yfinance 在本机网络不可达**，A 股源（tencent 等）正常；服务端启动预检约 60–90 秒
- 当前不接实盘；`src/live/` 与 `src/trading/` 视为冻结区
- 本地对上游的改动记在 [docs/README.md](docs/README.md) 的「本地改动」小节
