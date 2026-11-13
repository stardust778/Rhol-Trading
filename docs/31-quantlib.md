# 31 · QuantLib 量化库

> 定位：190+ 个纯函数量化计算 | 规模：`agent/src/quantlib/` 19k 行 / 26 模块 | 触发词：VaR、归因、因子模型、期权定价、绩效

## 摘要

- 26 个模块、约 190 个函数，**纯函数无状态**，直接 import 子模块
- `__init__.py` 故意不 import 任何东西：`from src.quantlib import options` 然后 `options.bs_price(...)`
- 三条数值约定必须记住：小数收益率、年化基期不统一、风险量是正数亏损
- Agent 通过 `quantlib_call` 工具访问，但只 dispatch `__all__` 里的名字

## 快速导航

| 我要算… | 模块 |
|---|---|
| 期权价格 / Greeks / IV / 障碍期权 | `options.py` |
| Heston、IV 曲面 | `volatility.py` |
| 债券定价 / YTM / 久期 / 收益率曲线 | `fixedincome.py` |
| Altman Z / Merton 违约距离 / CDS | `credit.py` |
| VaR / CVaR / 回撤 / EVT | `risk.py` |
| VaR 回测（Kupiec/Christoffersen/巴塞尔灯） | `var_backtest.py` |
| Deflated Sharpe / PBO / FDR | `multipletesting.py` |
| Purged CV / 泄漏检测 | `crossvalidation.py` |
| 风格暴露 / 因子收益 | `factormodel.py` |
| 因子中性化 / 截面 PCA | `neutralization.py` |
| 多因子合成 / walk-forward IC | `combination.py` |
| Brinson 归因 / Carino 链接 | `attribution.py` |
| 事件研究 CAR/CAAR | `eventstudy.py` |
| Amihud / Kyle / Roll / VPIN | `microstructure.py` |
| 冲击成本 / 滑点 | `impact.py` |
| HRP / ERC / 逆方差 | `portfolio.py` |
| Copula | `copula.py` |
| ADF / 协整 / OU 半衰期 / GARCH / 马尔可夫 | `timeseries.py` |
| TWR / Dietz / XIRR | `performance.py` |
| TVPI / DPI / PME / waterfall | `fundmath.py` |
| 单位换算 | `units.py` |

## 详细说明

### 三条数值约定

1. **收益率一律小数**：`0.083` = 8.3%，不是 8.3
2. **年化基期不统一**：
   - `risk.TRADING_DAYS_PER_YEAR = 252`、`timeseries` 默认 252、股票引擎 252
   - `performance.DAYS_PER_YEAR = 365.0`（XIRR/Excel 惯例）、加密 365
   - MT5 数据 260
   - **别拿 252 的 Sharpe 去配 365 的 XIRR**
3. **风险量是正数亏损**：VaR 不做 0 截断，无亏损样本会得到负的"亏损"。断言 `cvar >= var`，**不要**断言 `var >= 0`

### 两个 `xirr` 不通用

| 函数 | 输入 | 行为 |
|---|---|---|
| `fundmath.xirr(CashFlowSeries)` | 现金流序列 | 有界窗口扫描，可能多根；抛 `XIRRError` |
| `performance.xirr((date, amount) pairs)` | 元组列表 | 二分求单根；抛 `UnsolvableRateError` |

### 通过 Agent 调用

工具 `quantlib_call(module=..., function=..., ...)`：
- 模块白名单 + 只看 `__all__`
- 拒绝 `export_*` 写入类函数
- 结果分页
- DataFrame 用 `{"__dataframe__": ...}` 包一层

## 陷阱

1. **模块没写 `__all__` 就从 Web/API/MCP 不可达**（`attribution.py:48` 记录了历史上真出过这事）
2. `units.compare_rates` 从不推断单位，必须显式说 decimal / percent / bp
3. `compute_decay_metrics`、`DecayEvaluator` 这类"没数据返回健康"的行为在 quantlib 之外（在 `strategy_store`），别混

## 测试

```bash
pytest agent/tests/quantlib -q                                          # 40 个文件，纯数学
pytest agent/tests/test_quantlib_tool.py agent/tests/test_quantlib_result_budget.py -q
```
