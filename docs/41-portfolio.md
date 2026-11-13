# 41 · 组合与持仓

> 定位：只读组合快照、FX、再平衡建议 | 规模：`agent/src/portfolio/` 4.1k 行 | 触发词：持仓、组合、再平衡、FX

## 摘要

- 纯只读：**没有任何下单通道**
- 汇率约定：每 1 USD 兑多少本币，`USD == 1`；`to_usd = value / rate`
- 缺汇率 → 抛错（绝不默认 1）
- 再平衡只输出**价值金额建议**，不产生订单

## 快速导航

| 我要… | 文件 |
|---|---|
| 看持仓快照结构 | `src/portfolio/normalization.py` |
| 看 FX | `src/portfolio/fx.py` |
| 看合并逻辑 | `src/portfolio/service.py:_combine_holdings` |
| 看再平衡 | `src/portfolio/rebalance.py:propose_rebalance` |
| CLI | `vibe-trading portfolio show` / `import-extraetf` / `rebalance` |
| 工具 | `portfolio_summary` | `portfolio_risk_xray` |

## 详细说明

- **仓位估值**：`market_usd = to_usd(qty × market_price)`；`price <= 0` → 标 `priced=False`、价值记 0（不会当成 USD）
- **多券商合并**：同一标的合并成一行，标 `duplicate_across_brokers`；一个源失败则该源贡献 0 且快照标记不完整
- **再平衡前置条件**：快照完整、FX 不陈旧、所有持仓有价、`unpriced_or_other_usd == 0`、纯多头
- **再平衡输出**：`current / target / drift / change_value`，`mode: "proposal_only"`，附 `limitations[]`

## 陷阱

1. 汇率缺失/非正数直接抛 `PortfolioContractError`，不要想"兜底成 1"
2. 目标权重必须是已持有的 `canonical_id` 或 `CASH`，且和为 1（±1e-8）
3. 快照不可变；重新拉取会生成新快照

## 测试

```bash
pytest agent/tests/test_portfolio_service.py agent/tests/test_portfolio_fx.py -q
pytest agent/tests/test_portfolio_rebalance.py -q
```
