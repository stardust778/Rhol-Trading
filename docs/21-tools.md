# 21 · 工具系统

> 定位：135 个工具定义的契约与自动注册（默认注册 122 个） | 规模：`agent/src/tools/` 50.4k 行 | 触发词：加工具、BaseTool、注册、MCP 工具

## 摘要

- 工具是 Agent 唯一的副作用入口
- 放进 `agent/src/tools/` 并继承 `BaseTool` 就**自动注册**，没有列表要改
- 契约：`execute(**kwargs) -> JSON 字符串`
- 两个默认值最容易踩：`is_readonly=True`、`repeatable=False`
- 默认懒加载：工具只进目录（描述截断到 80 字符），模型得先 `load_tools`

## 快速导航

| 我要… | 位置 |
|---|---|
| 看契约 | `agent/src/agent/tools.py:13` `BaseTool` |
| 看注册逻辑 | `agent/src/tools/__init__.py:77` `build_registry` |
| 加工具 | `agent/src/tools/<名字>_tool.py` |
| 让新工具开箱可用 | `agent/src/agent/tool_loading.json` 的 `initial_tools` |
| 暴露到 MCP | `agent/mcp_server.py` |
| 过滤工具 | `build_filtered_registry` / `VIBE_TRADING_DENY_TOOL_PREFIXES` |

## 详细说明

```python
class BaseTool(ABC):
    name: str = ""                  # 唯一标识，重复会静默覆盖
    description: str = ""           # 懒加载下截断到 80 字符 —— 要短而准
    parameters: dict = {}           # JSON Schema
    repeatable: bool = False        # 能否被重复调用
    is_readonly: bool = True        # 只读 → 可并行执行 + 可缓存重放
    deterministic: bool = False     # 纯函数 → 相同参数命中缓存
    replay_after_compaction: bool = False

    @classmethod
    def check_available(cls) -> bool:   # 依赖检查（缺 key/包时返回 False）
        return True

    @abstractmethod
    def execute(self, **kwargs) -> str: ...   # 必须返回 JSON 字符串
```

### 注册流程

1. `_discover_subclasses()` import `agent/src/tools/*.py` 全部模块
2. 遍历 `BaseTool.__subclasses__()`，收 `name` 非空的类
3. `check_available()` 过滤
4. 按类名硬编码注入依赖（RememberTool / 后台任务 / goal / session / swarm）
5. MCP 远程工具追加（命名 `mcp_<server>_<tool>`）

### 加一个工具（5 步）

```python
# agent/src/tools/foo_tool.py
from src.agent.tools import BaseTool
import json

class FooTool(BaseTool):
    name = "foo"
    description = "一句话说清干什么、输入是什么、返回什么"
    parameters = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
    is_readonly = True        # 有副作用就必须改 False
    repeatable = True         # 能否重复调

    def execute(self, x: str) -> str:
        return json.dumps({"ok": True, "x": x}, ensure_ascii=False)
```

1. 写文件（不用注册）
2. 设对 `is_readonly` / `repeatable`
3. （可选）`check_available()` 检查可选依赖
4. （可选）加进 `tool_loading.json` 的 `initial_tools` 让模型无需 `load_tools`
5. （可选）在 `mcp_server.py` 加 `@mcp.tool` 包装暴露给 MCP 客户端

### 现有工具分组（速查）

| 组 | 代表工具 |
|---|---|
| 行情/数据 | `get_market_data` `get_stock_profile` `screen_market` `iwencai_search` `get_sector_info` |
| A 股特色 | `get_dragon_tiger` `get_fund_flow` `get_northbound_flow` `get_margin_trading` `get_cn_announcements` `get_lockup_expiry` `get_shareholder_count` `get_block_trades` |
| 回测/因子 | `backtest` `generate_backtest_config` `scaffold_signal_engine` `factor_analysis` `alpha_*` |
| 技术分析 | `technical_indicators` `pattern` |
| 基本面 | `get_financial_statements` `get_fundamentals` `get_research_reports` |
| 交易复盘 | `analyze_trade_journal` `extract_shadow_strategy` `run_shadow_backtest` `render_shadow_report` |
| 研究管理 | `start_research_goal` `research_lab` `sdm_register` `save_research_artifact` |
| 文件/系统 | `read_file` `write_file` `edit_file` `bash` `load_skill` |

## 陷阱

1. **`is_readonly` 默认 True**：写工具忘改 → 被并行执行且被缓存重放（严重）
2. **`repeatable` 默认 False**：合法重复调用被静默挡回"已完成"
3. **同名工具静默覆盖**，后发现的赢，无警告
4. **定义在 `src/tools/` 之外的工具不会被发现**；模块 import 失败也只 warning，模型调用时才体现为"工具不存在"
5. **MCP 侧是手写的 75 个 `@mcp.tool` + 10 个镜像类**，不是从注册表生成 —— 两边都要加
6. `mcp_server.py` 的 `_get_registry()` 在 `main()` 里**预热**是必需的，否则首次 `tools/call` 会在 FastMCP 线程里死锁（有 `test_mcp_server_smoke.py` 守着）

## 测试

```bash
pytest agent/tests/test_deferred_tool_loading.py agent/tests/test_registry_mcp_integration.py -q
pytest agent/tests/test_mcp_server_smoke.py -q
# 注意：agent/tests/test_registry.py 测的是数据 loader，不是工具注册表
```
