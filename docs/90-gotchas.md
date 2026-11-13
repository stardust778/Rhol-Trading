# 90 · 全局陷阱清单

> 踩坑时先查这里。按"会静默出错"到"会报错"排序。

## 静默出错（最危险，不报错但结果错）

| # | 陷阱 | 怎么发现 |
|---|---|---|
| 1 | 策略里再 `.shift(1)` → 双延迟 | runner 抛 `signal_timing_double_delay`；但只在检测到 shift 时 |
| 2 | `position_adjustment` 默认 `"hold"` 吞掉调仓 | 看 `dropped_target_adjustment_count` |
| 3 | 工具 `is_readonly` 默认 True → 写工具被并行+缓存 | 代码审查；无测试会失败 |
| 4 | 工具 `repeatable` 默认 False → 合法重复调用被挡 | 表现为"已完成"假结果 |
| 5 | 市场引擎没加 `_MARKET_PATTERNS` 正则 → 静默套用 A 股/加密规则 | run 会"成功"，但规则完全错 |
| 6 | 价格口径混用（减法复权 vs 乘性复权） | `mixed_caliber_warning`；run_card 的 `data_sources` |
| 7 | `source="auto"` 没配 benchmark → 回退等权篮子 | run_card warning；`benchmark_kind` |
| 8 | 配置打错字只警告，按默认值继续跑 | `runner.py` 的 unknown-key 警告 |
| 9 | 同工具名静默覆盖 / 同名 skill 静默覆盖内置 | 无警告 |
| 10 | 系统提示词里写死的数字（"29 个团队"）会漂移 | 以代码为准 |
| 11 | `warmup_bars=0` 时回填 start_date 会被计入评分 | 看 run_card 的评估窗口 |

## 会报错但信息容易误导

| # | 陷阱 | 说明 |
|---|---|---|
| 12 | `state.json` 只有工具层写 | 手跑 `python -m backtest.runner` 有指标但证据链认为"没跑过" |
| 13 | `agent/tests/test_registry.py` 测的是**数据 loader** | 工具注册表的测试在 `test_deferred_tool_loading.py` |
| 14 | `API_AUTH_KEY` 一设，`/docs` 返回 404 | 故意的，不是坏了 |
| 15 | 两个 `xirr` 异常类型不同 | `XIRRError` vs `UnsolvableRateError` |
| 16 | `ir` 有两个含义 | `information_ratio`（回测）≠ `mean(IC)/std(IC)`（因子） |
| 17 | `TOKEN_THRESHOLD` 已废弃 | 改它没用，用 `VIBE_TRADING_CONTEXT_WINDOW` |
| 18 | `get_env_config()` 是单例 | 改 env 后必须 `reset_env_config()` |
| 19 | `.env` 只加载第一个存在的文件 | `~/.vibe-trading/.env` 会盖住 `agent/.env` |
| 20 | `serve` 的 host/port 默认值与 CLI 声明不一致 | 实际 `127.0.0.1:8000` |
| 21 | `--dev` 打印 5173，实际 5899 | Vite 配置写死 5899 |

## 架构性限制

| # | 限制 |
|---|---|
| 22 | **单进程假设**：SSE ticket + 事件环形缓冲都在进程内，`--workers > 1` 会坏 |
| 23 | 每轮对话都建 run 目录（含纯文本回复）→ `GET /runs` 噪音大 |
| 24 | Agent 与回测是**两条链**，只通过磁盘交换数据 |
| 25 | Swarm 没有成本上限，只有 token 记账；`run_swarm` 同步阻塞 |
| 26 | 回测在子进程跑，超时（默认 1800s）会杀进程但保留部分产物 |
| 27 | `docs/` 是 gitignored 的内部文档目录，进不了仓库 |

## 数值约定

| # | 约定 |
|---|---|
| 28 | 收益率一律小数（0.083 = 8.3%） |
| 29 | 年化基期：252（股票/risk）/ 365（XIRR/加密）/ 260（MT5） |
| 30 | 风险量是**正数亏损**；断言 `cvar >= var`，不要断言 `var >= 0` |
| 31 | 汇率是"每 1 USD 兑多少本币"，`USD == 1`，`to_usd = value / rate` |
| 32 | 因子 bench 的 IC 是按日 Spearman，<5 个标的的日期丢弃 |

## 数据质量

| # | 说明 |
|---|---|
| 33 | `sp500` / `csi300` 用当前成分 → 幸存者偏差（标志位会亮） |
| 34 | `sina` / `alphavantage` / `longbridge` / `b3_cotahist` 是**不复权**数据 |
| 35 | 长停牌超过 ffill 上限（5/10 根）会变 NaN 被剔除 |
| 36 | 手数取整可能归零 → 该标的不产生成交但 run "成功" |
| 37 | 分钟线 + `fundamental_fields` 默认被拒 |

## 文档漂移

| # | 说明 |
|---|---|
| 38 | 大量 docstring 引用 `SPEC.md §…`，但**仓库里没有 SPEC.md** |
| 39 | 声称 "88 个 skill"，实际 89 个目录 |
| 40 | `guides/capabilities.md` 的项目结构图略陈旧（写 11 个引擎 / 122 工具） |

真契约永远是：**代码 + 测试**。
