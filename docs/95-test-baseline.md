# 测试基线与已知失败

> 上面全量基线记录。改代码前先看这里，避免把"上游已知失败"当成自己改坏的。

## 命令

```bash
cd /Users/lirihao/Rhol-Trading && source .venv/bin/activate
python -m pytest --ignore=agent/tests/e2e_backtest \
  --ignore=agent/tests/test_e2e_harness_v2.py --tb=short -q
```

## 基线（2026-11-13，v0.1.19）

| 指标 | 值 |
|---|---|
| 通过 | **21,848** |
| 失败 | **9**（装 `[stats]` 前是 12） |
| 跳过 | 112 |
| 耗时 | 5 分 48 秒 |

## 已知失败及归因（都不是环境问题，是上游测试漂移）

| 数量 | 测试 | 原因 | 影响 |
|---|---|---|---|
| 7 | `test_get_market_data_size.py` | 生产代码现在把 `_get_loader()` 的返回当**工厂**调用，测试的 fake 仍返回带 `.fetch` 的实例 → `'L' object is not callable` | 不影响功能，仅测试过时 |
| 1 | `test_strategy_adaptation_workflow.py::test_real_local_backtest_to_child_evidence` | 测试 fixture 给美股设了 `commission`，而 `global_equity.py` 现在**明确拒绝**美股 commission | 测试 fixture 过时 |
| 1 | `test_swarm_m4_e2e.py::test_run_worker_uses_remote_mcp_tool...` | 依赖一个 `mcp_kb_search` MCP 服务，未配置 → 被 registry 丢弃 | 需要外部 MCP 服务 |

### 已修复（装 extra 即可）

| 数量 | 测试 | 修复方式 |
|---|---|---|
| 3 | `test_ou_missing_lag_pairs_regressions.py` | `pip install -e ".[stats]"`（statsmodels + arch） |

## 结论

- 涉及 **A 股回测 / 数据源 / 因子 / 引擎** 的测试全部通过
- 9 个失败集中在：一个过时的 MCP 包装测试组、一个过时的美股 fixture、一个需要外部服务的 e2e
- 若要修，最小改动是更新那 7 个测试的 fake loader 接口，和 1 个 fixture 去掉 `commission`（都可提 upstream PR）
