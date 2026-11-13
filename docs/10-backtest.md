# 10 · 回测引擎

> 定位：策略 → 逐 bar 撮合 → 指标 → 产物 | 规模：`agent/backtest/` 33.5k 行 | 触发词：引擎、撮合、涨跌停、T+1、费用、metrics

## 摘要

- `BaseEngine` 持有全部状态（资金/持仓/成交/权益），子类只是**规则书**
- 子类必须实现 3 个方法：`can_execute` / `round_size` / `calc_commission`
- 12 个市场引擎 + 1 个期权引擎；A 股是 `china_a.py`
- 时序约定：信号 `t` 收盘算，`t+1` 开盘成交，**引擎自己已经 shift 过**

## 快速导航

| 我要… | 文件 | 备注 |
|---|---|---|
| 看 A 股规则 | `agent/backtest/engines/china_a.py` | T+1、涨跌停、手数、税费都在这 |
| 加一个市场 | `engines/<名字>.py` + `runner.py:_select_market_engine` + `_market_hooks.py:_MARKET_PATTERNS` | **三处都要改** |
| 改撮合主循环 | `engines/base.py:run_backtest` (:981) | 1500 行的核心 |
| 改指标 | `backtest/metrics.py` | |
| 加优化器 | `backtest/optimizers/<名字>.py` | 暴露 `optimize(ret, pos, dates, **params)` |
| 加约束 | `backtest/constraints.py` 的 `_TYPES` | `MaxWeight`/`MinWeight`/`GroupExposure` |
| 看产物格式 | `engines/base.py:_write_artifacts` (:2388) | |
| 做统计验证 | `backtest/validation.py` | Monte Carlo / bootstrap / walk-forward |

## 详细说明

### 引擎清单

`china_a` · `global_equity`（US/HK/CA/UK 按 `market` 分派）· `india_equity` · `korea_equity` · `vietnam_equity` · `brazil_equity` · `argentina_equity` · `crypto` · `china_futures` · `global_futures` · `forex` · `composite`（跨市场共享现金）
\+ `options_portfolio`（独立路径 `run_options_backtest`）

### 抽象接口（`engines/base.py:538`）

```python
class BaseEngine(ABC):
    # 必须实现
    def can_execute(self, symbol, direction, bar) -> bool          # :660 交易规则闸门
    def round_size(self, raw_size, price) -> float                 # :673 手数取整
    def calc_commission(self, size, price, direction, is_open) -> float  # :700 费用

    # 常用钩子（可选覆盖）
    apply_slippage  on_bar  available_cash  limit_band  historical_base_price
    prepare_market_data  before_rebalance_bar  after_rebalance_bar  _engine_diagnostics
```

### A 股规则（`china_a.py`，作为模板读）

| 规则 | 实现 |
|---|---|
| 禁止做空 | `can_execute` 对 `direction == -1` 直接 False |
| T+1 | 卖出时若 `pos.entry_time.date() == 当前 bar 日期` → 拒绝 |
| 涨跌停 | 用**上一交易日的基准价**（`pre_close` 或前收）算区间，禁止用当根 close（那是前视） |
| 涨停幅度 | 主板 10%，创业板/科创板 20%（`300/301/688/689`），北交所 30%（`4/8/920`） |
| 手数 | 主板/创业板 100 股整数倍，科创板最低 200 后 1 股递增，北交所 100 后 1 股递增 |
| 佣金 | `max(成交额 × 2.5bp, ¥5) + 过户费 1e-5 + 印花税 5bp（仅卖出）` |
| 滑点 | `price × (1 + direction × 0.001)`，`direction=+1` 对买入是不利的 |

### 加一个市场引擎 = 四步（缺一不可）

1. 子类化 `BaseEngine`，实现 3 个抽象方法
2. `runner.py:_select_market_engine`（:1784-1918）加路由分支（有优先级顺序）
3. `engines/_market_hooks.py:_MARKET_PATTERNS`（:398-455）加正则
4. 数据源的 `markets` 集合 + `FALLBACK_CHAINS` 里加链条

**漏掉第 3 步的后果**：symbol 会被静默套用 A 股或加密规则，回测"成功"但结果无意义（`runner.py:1895-1910` 有注释说明）。

### 产物

| 文件 | 内容 |
|---|---|
| `ohlcv_<code>.csv` | 输入 K 线 |
| `equity.csv` | `ret, equity, drawdown, benchmark_equity, active_ret` |
| `positions.csv` | **实际执行权重**（撮合后、规则后） |
| `target_positions.csv` | 信号/优化器**请求**的权重（被挡的单子在这） |
| `trades.csv` | 每个回合 2 行（entry/exit），含 pnl |
| `fills.jsonl` | 不可变成交证据（价格/数量/费用/拒单原因） |
| `metrics.csv` | 标量指标 |
| `risk_xray.*` `rebalance_notes.*` `validation.json` | 风险透视 / 再平衡审计 / 统计验证 |

run 根目录另有 `run_card.json` / `run_card.md`（config_hash、strategy_hash、data_sources、annualisation、citations）和 `state.json`。

### 主要指标（`metrics.py:606-775`）

`final_value, total_return, annual_return, max_drawdown, sharpe, calmar, sortino, win_rate, profit_loss_ratio, profit_factor, max_consecutive_loss, avg_holding_days, trade_count, benchmark_return, excess_return, information_ratio, tracking_error, benchmark_beta, avg_turnover, total_turnover`
\+ 引擎追加：`unfilled_plan_rejections(_by_symbol)`、`by_symbol`、`by_exit_reason`、`target_change_count`、`rebalance_executed_*`、`dropped_target_adjustment_count`、`risk_xray_*`、`execution_costs`、`lot_assumptions`、`crypto_funding_pnl`

## 陷阱

1. **再 shift 一次 = 双延迟**：引擎已执行 `t+1` 开盘成交，runner 会抛 `signal_timing_double_delay`
2. **美股设 `commission` 直接抛错**：美股用 `slippage_us`（默认 5bp），券商佣金为 0
3. **`warmup_bars` 默认 0**：靠回填 `start_date` 扩窗口会被计入评分
4. **手数取整可能归零**：目标仓位不足一手 → 什么也不做但 run 仍"成功"，看 `unfilled_plan_rejections_by_symbol`
5. **`_align` 的 ffill 有上限**（单市场 5 根 / 跨市场 10 根），长停牌会变 NaN 被剔除；估值另用无上限 ffill，两个矩阵不同是故意的
6. **基准会被静默替换**：`source="auto"` 且没配 `benchmark` 时回退到等权篮子，`benchmark_return` 就不是指数收益（run_card 有 warning）
7. **配置打错字只警告不报错**（`extra="allow"`），会按默认值继续跑

## 测试

```bash
pytest agent/tests/test_base_engine.py agent/tests/test_engine_robustness.py -q
pytest agent/tests/test_china_a_engine.py agent/tests/test_china_a_board_order_grid.py -q
pytest agent/tests/test_metrics.py agent/tests/test_run_card.py agent/tests/test_validation.py -q
```
