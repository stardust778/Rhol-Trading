# 30 · 研究与策略生命周期

> 定位：目标 → 实验 → 证据 → 策略库 → 衰减监控 | 规模：`src/research_lab` `src/strategy_*` `src/goal` `src/swarm` 等 | 触发词：策略库、SDM、衰减、swarm、研究目标

## 摘要

- 核心闭环：`goal`（目标+证据）→ `research_lab`（冻结快照上做实验）→ `backtest` → `sdm_register`（入库）→ `evidence`（按市场状态落证据）→ `decay`（衰减）→ `adapt`（克隆改良）
- 策略库是 SQLite，证据是另一个 SQLite，两者不要混
- Agent 只能通过工具访问，**写权限有限**：登记策略可以，改 mandate 不行
- Swarm 是 30 个 YAML 团队，**没有成本上限**，只有 token 记账

## 快速导航

| 我要… | 工具 / 文件 |
|---|---|
| 登记一个策略 | `sdm_register` → `src/strategy_store/sqlite_store.py` |
| 看策略状态 | `sdm_status` |
| 扫衰减 | `sdm_decay_scan` → `src/strategy_store/decay.py` |
| 克隆改良 | `adapt_strategy` |
| 在冻结快照上做实验 | `research_lab`（`cost_sensitivity` / `walk_forward` / `factor_audit` / `replay`） |
| 查某策略在某市况下的证据 | `query_strategies` / `get_strategy_evidence` |
| 建研究目标 | `start_research_goal` |
| 跑多 Agent 团队 | `run_swarm`；预设 `src/swarm/presets/*.yaml` |
| 定时研究 | `scheduled_research` + `src/scheduled_research/playbooks/*.md` |

## 详细说明

### 存储位置

| 子系统 | 存储 |
|---|---|
| 策略库 SDM | SQLite `~/.vibe-trading/strategy_store.db`，表 `artifacts` / `bench_history` / `decay_snapshots` / `adaptation_bindings` |
| 证据 | SQLite `strategy_discovery.db`，表 `strategy_regime_evidence`（键：strategy_id + regime） |
| 目标账本 | SQLite：`goals` / `goal_claims` / `goal_criteria` / `goal_evidence` |
| 假设 | `~/.vibe-trading/hypotheses.json` |
| 研究产物 | SQLite 索引 + 不可变版本（`identity_hash` UNIQUE） |
| Swarm 运行 | `.swarm/runs/{run_id}/`（`run.json` / `events.jsonl` / `tasks/` / `inboxes/` / `artifacts/`） |
| Research Lab 作业 | `runs/study-<32hex>/{study.json,report.json,execution.lock}` |

### 策略状态机

`created → benching → active → monitoring → decayed → disabled`

衰减判定（`decay.py`，纯函数，取最差项）：
- 阈值 `ic_ratio` .7/.5/.3、`ir` 1.0/.5/.1、`ic_pos` .55/.45/.35、`sharpe` 1.0/.5/0.0
- active → monitoring：3 次非健康
- monitoring → decayed：2 次 decayed+
- monitoring → active：1 次 healthy
- decayed → disabled：3 次 critical

### Swarm 预设格式

```yaml
name: quant_strategy_desk
agents:
  - id: screener
    role: 筛选
    system_prompt: "..."
    tools: [screen_market]
    max_iterations: 50
    timeout_seconds: 1800
tasks:
  - id: screen
    agent_id: screener
    prompt_template: "筛选 {market} 的候选股"
  - id: review
    agent_id: reviewer
    depends_on: [screen]
    prompt_template: "复核上游结论：{upstream_context}"
```

- 层内并行（`max_workers=4`），层间按拓扑序
- `run_swarm` **同步阻塞**整轮对话直到跑完，无流式中间结果
- 两种模板语法并存：swarm 用 `{var}`，scheduled-research playbook 用 `{{var}}`

### Skill

89 个目录，`SKILL.md` frontmatter 只有 3 个键：`name` / `description` / `category`（不是用 YAML 库解析）。
加载顺序：`~/.vibe-trading/skills/user/` 优先 → 内置 `agent/src/skills/`。**同名用户 skill 会静默覆盖内置**。
加 skill = 建目录，无注册步骤。

## 陷阱

1. **`compute_decay_metrics` 在 <3 条记录时返回全 None，而 `evaluate_decay()` 无输入时返回 HEALTHY** —— 会
   把"没数据"报成"健康"。先调 `has_decay_inputs()`
2. **`ic_ratio` 只在 baseline > 0 且 IC 记录 ≥10 条时才计算**；3-9 条时基线和滚动窗口重叠，"没衰减"是算术假象
3. **`manual` 类型的 bench 必须排除在衰减之外**（`DECAY_BENCH_TYPES`），否则临时重跑会移动基线
4. **策略名 + universe 唯一**：重复登记抛 `ValueError`
5. **`ValidationStatus.APPROVED` 只能从 `VALIDATED` 迁移**；登记时 `intended_use` 和 `limitations` 都不能为空
6. **证据表初始为空**，facade 拒绝在空表上评估市况 —— "查不到"不是 bug
7. **Research Lab 作业是单属主**：`execution.lock` + `owner_pid` 存活检查；worker 被杀后 `job_id` 需要重新开

## 测试

```bash
pytest agent/tests/test_strategy_store.py agent/tests/test_strategy_store_adaptation.py -q
pytest agent/tests/test_strategy_discovery_models.py -q
pytest agent/tests/test_research_lab_service.py agent/tests/test_research_lab_execution.py -q
pytest agent/tests/test_swarm_presets.py agent/tests/test_skills.py -q
```
