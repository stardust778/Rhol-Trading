# 60 · A 股工作流（日常主用）

> 定位：复盘 / 选股 / 策略研究 / 交易复盘 四条日常流程 | 触发词：今天行情、选股、复盘、龙虎榜、涨停
> 实盘不接入，实际操作手动完成。

## 摘要

- 这个项目是**研究工具**，不是交易终端：没有实时行情，日频为主
- A 股数据免费可用（akshare/baostock/tencent/sina/eastmoney）；`TUSHARE_TOKEN` 可提升质量并解锁 PE/PB/ROE 与财报字段
- 四条流程各有对应的工具组合，下面给了可直接复制的提示词
- 交易复盘是它的差异化能力：从你的成交记录里反推策略，再回测对比

## 一、每日行情复盘

**可用工具**

| 工具 | 内容 |
|---|---|
| `get_market_data` | 指数 / 个股 OHLCV |
| `get_sector_info` | 板块行情与成分 |
| `get_fund_flow` | 主力/散户资金净流入 |
| `get_northbound_flow` | 北向资金（沪深股通） |
| `get_dragon_tiger` | 龙虎榜买卖席位 |
| `get_margin_trading` | 两融余额与变动 |
| `get_cn_announcements` | 当日公告 |
| `get_stock_news` / `sentiment` | 新闻与情绪 |
| `technical_indicators` / `pattern` | 技术指标与形态 |

**提示词示例**

```
复盘今天 A 股：先给主要指数涨跌和成交额，再看板块涨跌前五/后五，
然后北向资金净流入、两融余额变化，最后列出今日龙虎榜净买入前 10
和它们的所属板块。用 markdown 表格，结论放最前面。
```

**配套 skill**：`sector-rotation`、`market-microstructure`、`technical-basic`、`candlestick`、`sentiment-analysis`、`eastmoney`、`akshare`

## 二、选股

**两条路径**

| 路径 | 工具 | 适合 |
|---|---|---|
| 条件筛选 | `screen_market` | 市值/PE/涨跌幅/成交额等硬条件 |
| 自然语言选股 | `iwencai_search` | "净利润连续三年增长、ROE>15%、股价在年线上方" |
| 板块内选 | `get_sector_info` + `get_fundamentals` | 先定板块再个股 |
| 因子排序 | `factor_analysis` + `alpha_bench` | 用量化因子打分 |

**提示词示例**

```
在沪深300 里筛出：PE(TTM) 在 10-25、ROE 连续 3 年 > 15%、
近 20 日涨幅 < 10%、日均成交额 > 2 亿。给出前 20 只，
每只附所属申万一级行业和最近一期营收增速。
```

**配套 skill**：`fundamental-filter`、`multi-factor`、`factor-research`、`valuation-model`、`ashare-pre-st-filter`（排除 ST/退市风险）

## 三、策略研究（回测）

**标准流程**

```
generate_backtest_config  → 生成 config.json
scaffold_signal_engine    → 生成 code/signal_engine.py 骨架
backtest                  → 跑，返回 metrics
factor_analysis           → 若要按因子分组看 IC/分层
research_lab              → 成本敏感性 / walk-forward / 复现
sdm_register              → 值得跟踪就入库，之后能扫衰减
```

**ChinaA 引擎自动生效的规则**（不用你写）：T+1、涨跌停（主板 10% / 创业科创 20% / 北交所 30%）、手数取整（100 股起）、佣金 + 过户费 + 卖出印花税、滑点 10bp。

**提示词示例**

```
写一个 A 股策略：在沪深300 成分股里，当 20 日动量排名前 10% 且
成交量突破 20 日均量 1.5 倍时买入，持仓 10 只等权，跌破 20 日线卖出。
回测 2018-01 到 2026-10，周频调仓，初始资金 100 万。
跑完给我年化、夏普、最大回撤，并做 5 折 walk-forward。
```

**关键**：配置里一定显式写 `position_adjustment`，并按需要加 `rebalance_mask`（如 `"W-FRI"`）。详见 [13-strategy-authoring](13-strategy-authoring.md)。

## 四、交易复盘（差异化能力）

**流水线**

```
analyze_trade_journal      解析券商导出 CSV（同花顺 / 东财 / 富途 / 通用）
   → 行为画像：持仓周期、胜率、处置效应、追涨、过度交易、锚定
extract_shadow_strategy    从盈利回合里提炼 3-5 条 if-then 规则
run_shadow_backtest        在 A 股/港股/美股/crypto 回测这些规则
   → 计算 delta-PnL（规则 vs 你的真实交易）
render_shadow_report       生成 HTML/PDF 报告（8 节 + 图表）
scan_shadow_signals        列出今天符合规则的标的
```

**提示词示例**

```
这是我的交易记录 CSV。先分析我的交易行为：平均持仓天数、胜率、
盈亏比，我是不是有处置效应（赚小钱跑、亏钱死扛）？再提炼出我
实际在用的买入规则，回测过去两年，看看如果不手动干预会怎样。
```

**注意**：需要的 CSV 字段 —— 成交日期、证券代码、买卖方向、成交价、成交数量（不同券商导出格式有差异，工具会自动识别；识别失败时手工整理成这五列即可）。

## 数据与限制

### 开箱可用（已实测注册成功）

`get_market_data` `get_sector_info` `get_fund_flow` `get_northbound_flow` `get_dragon_tiger` `get_margin_trading` `get_stock_news` `sentiment` `technical_indicators` `pattern` `get_financial_statements` `get_fundamentals` `get_research_reports` `get_stock_profile` `screen_market` `get_block_trades` `get_lockup_expiry` `get_shareholder_count` `get_institutional_holdings` `backtest` `factor_analysis` `generate_backtest_config` `scaffold_signal_engine` `alpha_*` `quantlib_call` `analyze_trade_journal` `extract_shadow_strategy` `run_shadow_backtest` `render_shadow_report` `scan_shadow_signals`

### 需要额外配置才能用

| 能力 | 工具 | 需要什么 |
|---|---|---|
| 自然语言选股（问财） | `iwencai_search` | `VIBE_TRADING_IWENCAI_KEY` |
| 公告 / 宏观 / 券商研报 / 基金净值 | `get_cn_announcements` `get_cn_macro_series` `search_broker_reports` `get_fund_nav` | Gildata token + 显式开启对应 feature |
| 美国宏观（FRED） | `get_macro_series` | `FRED_API_KEY` |
| 台湾股票 | `get_taiwan_stock_data` | 本地 SQLite 快照 |

### 通用限制

| 项 | 说明 |
|---|---|
| 免费数据 | akshare / baostock / tencent / sina / eastmoney，无需 key |
| 提升质量 | 配 `TUSHARE_TOKEN`：支持 `extra_fields`（PE/PB/ROE/市值）和 `fundamental_fields`（财报 PIT） |
| 频率 | 日频为主；分钟线支持但数据量大（1m 建议 ≤30 天，1H 建议 ≤1 年） |
| 实时性 | **不是实时行情**，复盘请用收盘后数据 |
| 复权 | tencent/akshare/eastmoney 是"减法前复权"，与 tushare 的乘性复权不可混用 |
| 财报时点 | 日线按公告日合并；分时 + 财报字段默认被拒（除非 `fundamental_subdaily: "next_day"`） |

## 常见的坑

1. 代码必须带后缀（`600519.SH` / `000001.SZ` / `430047.BJ`）
2. 别把 `position_adjustment` 留空 —— 默认 `hold` 会吞调仓
3. 回测跑通 ≠ 逻辑对，去 `artifacts/fills.jsonl` 核对首笔成交日期
4. 涨跌停/停牌导致的未成交会在 `unfilled_plan_rejections_by_symbol` 里，别当成 bug
