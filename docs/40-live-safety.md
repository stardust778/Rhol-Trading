# 40 · 实盘与风控（当前冻结）

> 定位：下单安全阶梯 | 规模：`src/live/` 9.7k 行 + `src/trading/` 22k 行 | 状态：**暂不启用，但不要破坏**
> 你目前手动交易，这篇只用于"以后要接时知道边界在哪"，日常不需要读。

## 摘要

- 四级阶梯：只读默认 → 纸交易 → mandate 授权 → 实盘
- 每一次下单都经过 `check_mandate` 的 11 步判定，第一处失败即拒绝
- 停机靠**文件存在性**：`~/.vibe-trading/live/HALT`
- 每条决策写两条审计：`audit.jsonl` + 哈希链 `audit_chain.jsonl`
- **写权限只能从 HTTP 来**，Agent 工具注册表里没有任何"写 mandate"的工具

## 快速导航

| 我要… | 位置 |
|---|---|
| 看判定逻辑 | `agent/src/live/enforcement.py:check_mandate` |
| 看下单闸门 | `live/order_guard.py`（MCP）/ `live/sdk_order_gate.py`（SDK） |
| 看授权模型 | `live/mandate/model.py` |
| 看停机哨兵 | `live/halt.py` |
| 看审计 | `live/audit.py` + `governance/ledger.py` |
| 看券商能力等级 | `trading/capability_matrix.py` |

## 详细说明

### 阶梯

| 级别 | 强制点 | 行为 |
|---|---|---|
| 0 发现期 | `live/classification.py:classify_tool` | 未标注的远程工具一律当 WRITE；halt 时写工具**不注册** |
| 1 只读默认 | `trading/profiles.py` + `service.place_order` | 只读 profile 下单直接 `_unsupported` |
| 2 纸交易 | `service.place_order`（`environment=="paper"`） | 直接调 connector，不过 mandate、不审计 |
| 3 mandate | `live/mandate/store.load_mandate` | 缺失/过期/版本不符 → DENY |
| 4 实盘 | `order_guard` / `sdk_order_gate` → `check_mandate` | 见下 |

### 判定链

```
load_mandate → 过期检查 → halt 检查 → 绑定账户 → 提取 OrderIntent
→ 数量换名义金额 → 读持仓+余额 → 每日下单锁 → 读当日计数
→ check_mandate:
     None                     → ALLOW
     kind=universe/instrument → DENY
     kind=quantitative        → PAUSE_FOR_REAUTH
→ 写审计；券商返回非 error 才 +1 当日计数
```

`check_mandate` 11 步：intent 合理性 → `exclude_symbols` → `allowed_instruments` → 期权硬拒 → `asset_classes` → 单笔名义金额 → 事后总敞口 → 总杠杆 → 当日笔数 → 资金 → 市值/ADV 下限。

### Mandate 字段

- `HardCaps`：`account_funding_usd` / `max_order_notional_usd` / `max_total_exposure_usd` / `max_leverage` / `allowed_instruments` / `max_trades_per_day`
- `UniverseConstraint`：`asset_classes` / `min_market_cap_usd` / `min_avg_daily_volume_usd` / `exclude_symbols`
- `ConsentMeta`：`created_at` / `consent_token_sha256` / `broker` / `account_ref` / `expires_at`
- `flatten_on_halt`：默认 False（只撤单不砸盘）

授权只能通过 `POST /mandate/commit`，且调整只能**收窄**不能放宽。

### 券商连接器

19 个，**没有基类**，是 package + module-level 函数约定：
`place_order` / `cancel_order` / `get_account_snapshot` / `get_positions` / `get_quote`，可选 `quantity_notional_usd`。

能力等级：实盘可下单 = alpaca / binance / etoro / futu / mt5 / okx / robinhood / tiger；仅纸交易 = dhan / kis / longbridge / shoonya / upbit / zerodha；只读 = ibkr / scalable / mstock。
改完跑 `python -m src.trading.capability_matrix` 重新生成文档表格。

## 不可协商（如果将来要接实盘）

1. 不加第二个 mandate 写入点；不让 halt 能被工具清除
2. 测试不要绕过闸门直接调 `connector.place_order`，要注入 fake 到 adapter/connector 缝
3. 未标注的远程工具永远不当只读；不给 live 券商 `enabled_tools=["*"]`
4. halt 在**调用时**检查，注册期省略只是纵深防御
5. 数据读不出来就 DENY
6. 密钥只进 keyring / TAP
7. 审计写失败不能让在途订单崩溃

## 现状

当前不使用实盘，所以：
- 不要创建 `~/.vibe-trading/live/mandate.json`
- 不要设 `HALT` 文件
- 修改 `src/live/` 或 `src/trading/` 前先看 `AGENT_CONTRIBUTOR_GUIDE.md` 的 High-Risk Surfaces

## 测试（改动时必跑）

```bash
pytest agent/tests/test_sdk_order_gate.py agent/tests/test_mandate_enforcement.py \
       agent/tests/test_killswitch_blocks_orders.py agent/tests/test_readonly_default.py -q
```
