# 12 · 因子 / Alpha Zoo

> 定位：478 个预置 alpha + IC/IR 评估 | 规模：`agent/src/factors/` 30.7k 行 | 触发词：因子、alpha、IC、IR、因子研究、alpha-zoo

## 摘要

- 一个 alpha = 一个文件：`zoo/<zoo>/<id>.py`，含 `__alpha_meta__` + `compute(panel)`
- 五族共 478 个：qlib158(154) / alpha101(101) / gtja191(191) / academic(12) / fundamental(20)
- 两道强制门：**纯度**（只许 pandas/numpy/scipy + factors.base）和**前视**（禁负 shift）
- 元数据用 AST 抽取，从不 import 模块 —— 所以坏文件不会拖垮 registry

## 快速导航

| 我要… | 文件 | 备注 |
|---|---|---|
| 浏览所有 alpha | `vibe-trading alpha list` 或工具 `alpha_zoo` | Web 页 `/alpha-zoo` |
| 看单个 alpha 定义 | `agent/src/factors/zoo/<zoo>/<id>.py` | |
| 加一个 alpha | 新建文件即可，无需注册 | 但要过两道门 |
| 跑 IC/IR | `alpha_bench` 工具 / `vibe-trading alpha bench` | |
| 改算子 | `agent/src/factors/base.py` | **会触发 warmup 对账警报** |
| 因子成本模型 | `agent/backtest/factor_costs.py` | 与引擎的逐笔费用模型不同 |

## 详细说明

### 一个 alpha 的结构

```python
__alpha_meta__ = {                    # AlphaMeta，frozen，extra="forbid"
    "id": "alpha_018",                # ^[a-z][a-z0-9]+_[a-z0-9_]+$
    "nickname": "量价背离",
    "theme": "volume_price",
    "formula_latex": "...",
    "columns_required": ["close", "volume"],
    "universe": "csi300",             # csi300 | sp500 | btc-usdt（也可加 equity_in/equity_kr）
    "frequency": "1D",
    "decay_horizon": 20,
    "min_warmup_bars": 60,
}

def compute(panel: dict[str, pd.DataFrame]) -> pd.DataFrame:
    # panel: code -> DataFrame(open/high/low/close/volume, index=date)
    # 返回：宽表 index=date, columns=codes
```

### 两道门（PR 必过）

| 门 | 测试文件 | 规则 |
|---|---|---|
| 纯度 | `agent/tests/factors/test_alpha_purity.py` | 只许 `pandas / numpy / scipy.* / src.factors.base / typing / math / dataclasses / __future__`；禁 `os sys subprocess socket urllib requests httpx pathlib open eval exec getattr(x,"__…")` |
| 前视 | `agent/tests/factors/test_lookahead.py` | 禁负 shift；`delta(df, d)` 对 `d < 1` 直接抛错 |

**NaN 策略**：NaN 必须传播，禁 `fillna(0)`，禁 `±inf`，常数窗口的 corr/cov 返回 NaN。

### 评估逻辑

- `ic_series` = 按日 Spearman 秩相关，**少于 5 个有效标的的日期丢弃**
- 前向收益：h=1 是 `close.pct_change().shift(-1)`；h>1 用**非重叠、尾部锚定**采样（避免 √h 的 t 值膨胀）
- 统计量：`ic_mean` / `ic_std` / `ir = ic_mean/ic_std` / `ic_positive_ratio` / `t_stat`
- 分类：`ic_mean>0.02 ∧ pos_ratio>=0.55 ∧ |t|>2` → **alive**；反向 → **reversed**；否则 **dead**
- 严格版 `bench_runner_strict.py` 另加配对随机对照 + OOS + deflated Sharpe

### 覆盖范围

`alpha101` / `qlib158` 同时打标 `equity_in`、`equity_kr`，可在印度、韩国股票上算；`gtja191` 仅中国市场。

## 陷阱

1. **`warmup_contracts.json` 钉住了 `base.py` 的 SHA**：改任何一个算子，所有 alpha 的审计失效直到重新对账 —— 这是故意的警报器
2. **`ir` 不是 Sharpe**：benched 的 `ir = mean(IC)/std(IC)`，和 `metrics.csv` 里的 `information_ratio` 是两个量
3. `deflated_sharpe_ratio` 作用在 IC 的 IR 上，不是收益 Sharpe
4. `quantlib_call` 只 dispatch `__all__` 里的名字；模块没写 `__all__` 就从 Web/MCP 不可达
5. `sp500` 用维基百科**当前成分股** → 有幸存者偏差（`survivorship_bias: True` 会标出来）；`csi300` 只有在提供历史成分时才 PIT

## 测试

```bash
pytest agent/tests/factors/test_alpha_purity.py agent/tests/factors/test_lookahead.py -q   # 两道门
pytest agent/tests/factors agent/tests/test_factor_operators.py -q
```
