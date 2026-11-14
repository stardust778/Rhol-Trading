# Vibe-Trading 项目地图（分层索引）

> 本地开发上下文，`docs/` 已列入 `.gitignore`，不会进仓库。
> 对应 `v0.1.19` / commit `283e300e`，核对于 2026-11-13。

## 30 秒认识

自然语言驱动的金融研究 Agent：用户说一句话 → LLM 自己写 `config.json` + `signal_engine.py` → 跑回测 → 出报告。可选接实盘券商（带 mandate 授权闸门，本项目暂时不用）。

**规模**：Python ~293k 行 + 前端 ~45k 行；937 个测试文件；135 个工具定义（运行时注册 122 个）；89 个 skill；478 个 alpha；12 个市场引擎 + 1 个期权引擎；28 个数据源；19 个券商连接器；30 个 swarm 团队。
**技术栈**：Python 3.11+ / FastAPI / LangChain+LangGraph / React 19 + Vite / SQLite + 文件系统。
**三个入口**：`vibe-trading`（CLI/TUI）、`vibe-trading serve`（Web + REST + SSE）、`vibe-trading-mcp`（MCP）。

## 这套文档怎么用

先读本页（约 75 行），然后**只读当前任务相关的 1 篇**（每篇 40–140 行）。不要整包阅读。

| 文档 | 一句话 | 什么时候读 |
|---|---|---|
| [01-architecture](01-architecture.md) | 对话链与回测链怎么交接，目录布局 | 第一次接触 / 理不清调用关系 |
| [10-backtest](10-backtest.md) | 回测引擎：规则、撮合、产物、指标 | 改引擎、看懂一次 run |
| [11-data-sources](11-data-sources.md) | 28 个数据源、降级链、价格口径 | 数据拉不到 / 加数据源 / 复权疑惑 |
| [12-factors](12-factors.md) | Alpha Zoo 478 因子、纯度与前视门 | 加因子、跑 IC/IR |
| [13-strategy-authoring](13-strategy-authoring.md) | **策略怎么写**：config.json + signal_engine | 写/改策略时必读 |
| [20-agent-runtime](20-agent-runtime.md) | ReAct 循环、上下文压缩、系统提示词 | 改 Agent 行为/预算 |
| [21-tools](21-tools.md) | 工具契约与自动注册 | 加工具 |
| [22-providers](22-providers.md) | LLM 接入抽象 | 换模型/加 provider |
| [30-research-strategy](30-research-strategy.md) | 目标→实验→证据→策略库→衰减 | 要做策略生命周期管理 |
| [31-quantlib](31-quantlib.md) | 190+ 量化纯函数 | 需要算 VaR/归因/因子模型 |
| [40-live-safety](40-live-safety.md) | 实盘安全阶梯（**当前冻结**） | 将来接实盘时再读 |
| [41-portfolio](41-portfolio.md) | 组合快照、FX、再平衡建议 | 看持仓/做再平衡 |
| [50-api-frontend](50-api-frontend.md) | 路由、鉴权、SSE、前端页面 | 改 Web/接自己的 UI |
| [60-a-share-playbook](60-a-share-playbook.md) | **A 股工作流**：复盘/选股/交易复盘 | 日常使用时读 |
| [90-gotchas](90-gotchas.md) | 跨模块陷阱清单 | 踩坑时先查这里 |
| [95-test-baseline](95-test-baseline.md) | 测试基线与 9 个已知失败 | 改代码前 / CI 报红时 |

## 三条典型路径

- **写/调策略** → 13-strategy-authoring →（拉不到数据时）11-data-sources →（看不懂指标时）10-backtest
- **改 Agent 行为** → 20-agent-runtime →（要加能力时）21-tools → 01-architecture
- **做 A 股日常工作** → 60-a-share-playbook

## 全局不变量（违反会**静默**出错）

1. 信号在 bar `t` 收盘计算，引擎自己在 `t+1` 开盘成交 —— **策略里再 `.shift(1)` 就是双延迟**
2. `position_adjustment` 默认 `"hold"`，会静默丢弃调仓；只有 `dropped_target_adjustment_count` 能看出来
3. `state.json` 由**工具层**写，引擎不写 —— 手跑 `python -m backtest.runner` 等于"没跑过"
4. 工具类里 `is_readonly` 默认 `True`、`repeatable` 默认 `False` —— 新增写工具必须显式改
5. `information_ratio`（回测指标）≠ `ir`（因子 bench 的 mean(IC)/std(IC)）
6. 收益率一律小数（0.083=8.3%）；年化基期 252/365/260 三种，不可混用

## 环境（已就绪）

| 组件 | 状态 |
|---|---|
| Python | **3.12.16**（Homebrew 系统级：`/opt/homebrew/bin/python3.12`） |
| venv | 项目内 `.venv/`（已 gitignore），pip 走清华镜像（`.venv/pip.conf`） |
| 项目依赖 | `pip install -e ".[dev]"` + `.[stats]` 完成，约 250 个包 |
| Node | **22.23.5**（brew `node@22`；注意你的 shell 把 Node 18 固定在 PATH 前面） |
| 前端 | `npm ci` + `npm run build` 完成，`frontend/dist/` 已生成 |
| LLM provider | ✅ `deepseek-v4-flash`（`~/.vibe-trading/.env`），**key 待填** |

```bash
cd /Users/lirihao/Rhol-Trading && source .venv/bin/activate

python -m pytest agent/tests/test_base_engine.py -q        # 冒烟，104 passed
# 填 key：编辑 ~/.vibe-trading/.env 的 DEEPSEEK_API_KEY=（或 Web → Settings → LLM）
vibe-trading                                               # CLI/TUI
vibe-trading serve --port 8899                             # Web（已构建，直接可用）
```

**前端命令**需要显式指定 Node 22（或先 `nvm use 22`）：

```bash
PATH=/opt/homebrew/opt/node@22/bin:$PATH npm run dev
```

### 已验证的能力边界

- ✅ A 股日线：`resolve_loader("a_share")` 默认走 tencent，实测取到 `000001.SZ` 18 根日线
- ✅ 行情 K 线页：`GET /api/market/ohlc` + 前端 `/market`，与回测共用 loader / 复权口径
- ✅ 交割单复盘：中文通用解析器（招商风格）+ `/api/journal/*` + 前端 `/journal`，成交落 SQLite 去重
- ✅ 缠论复盘：`czsc`（可选依赖 `pip install -e ".[chan]"`）算分型/笔/中枢，`/api/chan/*` 逐笔判定买卖点结构
- ✅ 多级别：1m / 5m / 30m / 60m / 日 / 周；分钟线走 Sina/Eastmoney 公开接口（`src/market_intraday.py`）
- ✅ 复盘画图：K 线上叠加笔（紫线）、中枢（紫色区间）、缠论买卖点（1B/2S…）与自己的 B/S 成交点
- ✅ 复盘判定：缠论结构 + 区间套（上一级别确认）+ 均线量价（MA20/多头排列/回踩缩量/放量突破）+ 后 5/10/20 日收益
- ✅ 回测引擎：104 个单测通过；因子门 + loader 契约 + run_card：973 passed / 23 skipped
- ⚠️ **Yahoo/yfinance 在你的网络下不可达**（预检会重试约 1 分钟才继续）→ 优先用 A 股数据源
- ⚠️ 服务端启动会做网络预检，首次启动约需 60–90 秒

### 本地改动（相对上游 HEAD）

- 新增 `agent/src/api/market_routes.py`（`GET /api/market/ohlc`）与 `frontend/src/pages/Market.tsx`（`/market`）。
- 新增 `agent/src/chan/analyzer.py`（缠论结构 + 逐笔判定）与 `agent/src/api/chan_routes.py`（`/api/chan/analysis|review|signals`）；
  前端 Journal 的个股图下方增加「缠论结构 + 逐笔点评」。依赖 `czsc>=1.0.2`（`.[chan]` extra，未安装时接口返回 503）。
- 行情页显示标的中文名（腾讯公开行情接口，A股/港股），MA 默认 5/10/20/30/55/99/128/225。
- 侧栏只保留 行情 / 交易复盘 / 账户持仓 / 定时任务（`navigation.ts` 里其余条目已注释，路由未删，取消注释即可恢复；`/` 重定向到 `/market`）。
- 交易复盘支持 `?symbol=000001.SZ` 深链，图表下方是缠论结构与逐笔点评（含区间套、均线量价、前瞻收益）。
- 新增 `agent/src/api/journal_routes.py`、`agent/src/journal/{store,analysis}.py` 与 `frontend/src/pages/Journal.tsx`（`/journal`）；
  `trade_journal_parsers.py` 增加中文通用交割单/对账单解析器 `cn_broker`，并让 CSV 加载器跳过券商导出前置的标题行。
- `frontend/src/components/options/PayoffComparisons.tsx`：3 处动态 i18n key 加 `as never`。
  上游 commit `d3f79ae4` 引入的类型错误会让 `npm run build` 失败（`npm run dev` 不受影响）。
  这是可提 upstream 的小 bug。
- 项目目录从 `Vibe-Trading` 改名为 `Rhol-Trading`：`.venv` 里的绝对路径（activate / console script / editable `.pth`，共 62 个文件）已改到新路径。

## 用户场景

主攻 **A 股**：每日行情复盘、策略研究、选股、交易复盘。实盘不接入，手动执行。详见 [60-a-share-playbook](60-a-share-playbook.md)。
