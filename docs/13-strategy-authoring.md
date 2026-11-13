# 13 · 策略编写（A 股）

> 定位：`config.json` + `signal_engine.py` 的确切契约 | 触发词：写策略、signal_engine、回测配置、选股策略
> 这是日常最高频的一篇。

## 摘要

- 一个策略 = **一个目录**：`config.json` + `code/signal_engine.py`
- `SignalEngine.generate(data_map)` 返回 `{code: Series}`，值域 `[-1, 1]`
- **信号不要自己 shift**：引擎已经做了 `t → t+1 开盘` 成交
- `position_adjustment` 必须显式声明，默认的 `hold` 会静默吞掉调仓
- A 股代码必须带后缀（`.SZ` / `.SH` / `.BJ`），否则会走错市场规则

## 快速导航

| 我要… | 位置 |
|---|---|
| 看完整契约原文 | `agent/src/skills/strategy-generate/SKILL.md`（261 行，**权威**） |
| 让 Agent 生成脚手架 | 工具 `scaffold_signal_engine` / `generate_backtest_config` |
| 跑回测 | 工具 `backtest`，或 `cd agent && python -m backtest.runner <run_dir>` |
| 看结果 | `<run_dir>/run_card.md`、`artifacts/metrics.csv`、`artifacts/fills.jsonl` |
| 做统计验证 | `config.validation` 或 `python -m backtest.validation <run_dir>` |

## 详细说明

### 最小可运行示例（A 股双均线）

`config.json`
```json
{
  "source": "auto",
  "codes": ["000001.SZ"],
  "start_date": "2018-01-01",
  "end_date": "2026-11-01",
  "warmup_bars": 60,
  "interval": "1D",
  "initial_cash": 1000000,
  "position_adjustment": "rebalance",
  "rebalance_mask": "W-FRI",
  "rebalance_tolerance": 0.05,
  "validation": {"walk_forward": {"n_windows": 5}}
}
```

`code/signal_engine.py`
```python
import pandas as pd

class SignalEngine:
    def __init__(self, fast: int = 10, slow: int = 30):
        self.fast, self.slow = fast, slow

    def generate(self, data_map: dict[str, pd.DataFrame]) -> dict[str, pd.Series]:
        out = {}
        for code, df in data_map.items():
            close = df["close"]
            fast = close.rolling(self.fast).mean()
            slow = close.rolling(self.slow).mean()
            signal = pd.Series(0.0, index=df.index)
            signal[fast > slow] = 1.0
            out[code] = signal          # 不要 .shift(1)
        return out
```

构造参数从 `config.json` 的 `signal_parameters` 注入（`{"fast": 10, "slow": 30}`）。

### `config.json` 字段（A 股常用）

| 字段 | 说明 |
|---|---|
| `source` | `"auto"` 最省事（按代码格式自动路由）；也可写 `tushare` / `akshare` / `baostock` |
| `codes` | `["600519.SH", "000001.SZ"]` |
| `start_date` / `end_date` | **数据窗口**；`start_date + warmup_bars` 才是**评估窗口** |
| `warmup_bars` | 指标预热根数，默认 0（= 全窗口计分，通常会高估） |
| `evaluation_start_date` | 与 `warmup_bars` 二选一，同时声明会被拒绝 |
| `initial_cash` | 默认 1,000,000 |
| `position_adjustment` | **必填**：`"rebalance"` 或 `"hold"` |
| `rebalance_mask` | 执行节奏，如 `"W-FRI"` / `"MS"` / 显式日期列表（仅 rebalance） |
| `rebalance_tolerance` | 漂移容忍带（仅 rebalance）。实测：恒定 20% 目标在 60 根 bar 上，`0.0`→60 次成交，`0.02`→12 次，`0.05`→5 次 |
| `extra_fields` | A 股日频估值：`["pe","pb","pe_ttm","ps_ttm","dv_ttm","total_mv","circ_mv","roe"]`（仅 tushare） |
| `fundamental_fields` | 财报 PIT：`{"income":["total_revenue","n_income"],"fina_indicator":["roe"]}` |
| `optimizer` | `equal_volatility` / `risk_parity` / `mean_variance` / `max_diversification` / `turnover_aware` / `null` |
| `interval` | `1D`（默认）/`1W`/`1M`/`1m`/`5m`/`15m`/`30m`/`1H`/`4H` |
| `validation` | `monte_carlo` / `bootstrap` / `walk_forward` |
| `artifact_id` + `bench_type` | 只有登记到策略库时才填；`initial`/`periodic` 才计入衰减监控 |

### `position_adjustment` 怎么选（最容易选错）

| 模式 | 行为 | 什么时候用 |
|---|---|---|
| `"rebalance"` | 每次目标变化都成交；权重漂移也会重新拉回 | 目标权重本身承载策略（优化器、风险预算、连续仓位） |
| `"hold"` | 同向持仓保持到离场/反向；**请求的调仓不执行** | 进出场承载策略，中间仓位只是副产品 |

**注意**：`rebalance` 下策略每根 bar 都重申目标 → 恒定目标也会每根 bar 成交（实测 40 根上涨序列产生 40 笔而非 1 笔）。用 `rebalance_mask` 表达节奏，不要用 `rebalance_tolerance` 硬凑。

### 信号语义

- `1.0` 满仓多 / `0.5` 半仓 / `0.0` 空仓 / `-1.0` 满仓空
- 整数 `{-1, 0, 1}` 兼容（等同于 -100% / 0% / 100%）
- 组合策略：选出 N 只后每只 `1/N`，未选中的给 0

### 硬性约束（违反会被 AST 扫描拦下或结果出错）

- Series 索引必须与输入 DataFrame 索引**完全对齐**
- 不得硬编码日期或股票代码（从 config 读）
- 不得有 `if __name__ == "__main__"` 块
- 纯 pandas/numpy，不引外部信号库
- **不要自己 shift**

## 陷阱

1. **双重延迟**：`.shift(1)` 或 `signal[i] = 条件[i-1]` 都会让每笔成交晚一根，runner 抛 `signal_timing_double_delay`。只有用户明确要求额外延迟时才用 `intentional_signal_delay_bars`
2. **A 股后缀**：`600/601/603` 开头 → `.SH`，其余 → `.SZ`；北交所 `.BJ`。不带后缀会被静默套错规则
3. **`hold` 丢调仓**：只体现在 `dropped_target_adjustment_count`（前 20 条明细），极易被忽略
4. **财报字段的时点**：日线上按公告日合并；分时 + `fundamental_fields` 被直接拒绝，除非设 `"fundamental_subdaily": "next_day"`
5. **回测成功 ≠ 逻辑正确**：`strategy-generate` skill 要求独立算出首次进出场的预期日期，再去 `artifacts/fills.jsonl` 核对，不要只看指标

## 测试

```bash
# 跑通一次（在 agent/ 下）
python -m backtest.runner /path/to/run_dir
# 相关单测
pytest agent/tests/test_signal_output_timing.py -q     # 信号时序 / 双延迟
pytest agent/tests/test_backtest_tool_state.py agent/tests/test_backtest_runner_security.py -q
```
