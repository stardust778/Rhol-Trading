# 11 · 数据源与行情

> 定位：28 个行情源 + 有序降级链 + 价格口径 | 规模：`agent/backtest/loaders/` | 触发词：拉不到数据、复权、qianfu、source、akshare、tushare

## 摘要

- 28 个数据源统一到一个 `fetch()` 协议，按市场组成**有序降级链**
- 降级顺序的原则：先低封 IP 风险的公开端点，后需要 key 的 REST
- 每个源都标了**价格口径**（前复权/后复权/不复权），混用会造假信号
- 缓存默认关闭；开启后只缓存 `end_date` 严格早于今天的区间
- A 股主用：tushare（可选 token）/ akshare / baostock / tencent / sina / eastmoney

## 快速导航

| 我要… | 文件 | 备注 |
|---|---|---|
| 看某市场用哪些源 | `agent/backtest/loaders/registry.py` 的 `FALLBACK_CHAINS` (:178) | 有序列表 |
| 加数据源 | `loaders/<名字>_loader.py` + `VALID_SOURCES` + `_loader_modules` | 三处 |
| 强制指定源 | `config.json` 的 `"source": "tushare"` | 见 13-strategy-authoring |
| 改降级顺序 | 环境变量 `MARKET_DATA_ORDER_<MARKET>` | 必须是默认链的**排列** |
| 查复权口径 | `registry.py` 的 `PRICE_CALIBER_BY_SOURCE` (:265) | |
| 开缓存 | `VIBE_TRADING_DATA_CACHE=1` | 默认关 |
| 自检数据源健康 | `python -m backtest.loader_health --output report.json` | |

## 详细说明

### 接口（`loaders/base.py:935`）

```python
name: str; markets: set[str]; requires_auth: bool
def is_available(self) -> bool
def fetch(self, codes, start_date, end_date, *, interval="1D", fields=None) -> dict[str, pd.DataFrame]
# 返回：code -> DataFrame(index: DatetimeIndex 名 trade_date; cols: open/high/low/close/volume + extras)
```

**共用工具**（别自己造）：`validate_date_range`、`validate_ohlc`（剔除 high<low / 价格越界 / ≤0）、`check_budget` + `retry_with_budget`（墙钟预算 + 只重试声明的瞬时异常）、`resample_bars`（1W/1M 由 1D 合成）、`cached_loader_fetch`。

### 注册

```python
@register            # registry.py:69 → LOADER_REGISTRY
class MyLoader: ...
```
`_ensure_registered()` 会 import `_loader_modules` 里所有模块，保证注册表非空。
**新增 loader 必须同时加进 `VALID_SOURCES`**，否则 `test_engine_robustness.py:469` 失败。

### 不许降级的源

`_NO_NETWORK_FALLBACK_SOURCES` = `local, gildata, tickerall, fmp, nobitex, wallex, b3_cotahist`
这些必须**硬失败**，因为"静默换成别的源"会让实验结果不可复现。

### 价格口径（最容易出事）

| 口径 | 源 | 含义 |
|---|---|---|
| `split_dividend_additive` | tencent / akshare / eastmoney（A 股） | 前复权是**减去**股息，是**平移**不是缩放 |
| 乘性复权 | tushare / yahoo / yfinance | 按比例缩放 |
| `raw`（不复权） | sina / alphavantage / longbridge / b3_cotahist | 分红表现为下跌 |

把 additive 和乘性混在一个篮子里，会造出**虚假的截面差异** → 因子 IC 直接失真。
`mixed_caliber_warning`（`registry.py:401`）就是为此存在；run_card 的 `data_sources` 记录**实际**服务的源，不是被要求服务的源。

### A 股数据源实际选择

| 源 | 需要 token | 特点 |
|---|---|---|
| `tushare` | 是（`TUSHARE_TOKEN`） | 质量最好，支持 daily_basic（PE/PB/ROE）和财报字段 |
| `akshare` | 否 | 免费，覆盖广，偶尔被限流 |
| `baostock` | 否 | 走 TCP 协议，绕过 HTTP 反爬 |
| `tencent` | 否 | 免费、稳定，只用 stdlib |
| `eastmoney` | 否 | 免费，有反爬 |
| `sina` | 否 | 免费，数据不复权 |
| `mootdx` | 否 | **2026-10-08 已从默认链移除** |

**只有 tushare 支持 `extra_fields`（PE/PB/ROE 等日频估值）和 `fundamental_fields`（财报 PIT 合并）**。

### 代码格式

- A 股：`000001.SZ` / `600000.SH` / `430047.BJ`（**必须带后缀**，引擎靠后缀路由；6 位纯数字能过校验但会走错规则）
- 港股：`700.HK`；美股：`AAPL.US`；加密：`BTC-USDT`（连字符，不是斜杠）

### 失败模式

- 反爬/封 IP 会**闩锁**（`stooq_loader.py:_latch`），不是简单重试
- 部分返回只补缺失的 symbol（不整批重拉）
- 全部服务不了才抛 `NoAvailableSourceError`，错误信息里带 `missing symbols` 和 `served symbols`

## 陷阱

1. `local:` 前缀选本地 loader，但下游看到的是去掉前缀的 symbol
2. `source="auto"` 下混合品种会**分源拉取**再合并，合并时口径可能不同
3. 缓存键含 `_LOADER_CACHE_VERSION`，改了 loader 逻辑记得升版本号，否则读到旧缓存
4. `MARKET_DATA_ORDER_*` 不是排列而只是子集 → 直接拒绝加载

## 测试

```bash
pytest agent/tests/test_loader_contract.py agent/tests/test_loader_retry_helpers.py -q
pytest agent/tests/test_loader_health.py agent/tests/test_ohlc_validation.py -q
pytest agent/tests/test_yahoo_loader.py agent/tests/test_tushare_loader.py -q
```
