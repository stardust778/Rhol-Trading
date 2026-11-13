# 22 · LLM Provider

> 定位：26 家 provider 归一化成一套流式 + 工具调用接口 | 规模：`agent/src/providers/` 6k 行 | 触发词：换模型、API key、deepseek、openai、provider

## 摘要

- `build_llm()` 返回 LangChain chat model；`ChatLLM` 再包一层做归一化
- 只要 OpenAI 兼容，加 provider 只需改两处配置
- 流式/重试/超时统一由 `stream_guard` 用"赛跑"方式处理
- 模型不会发原生 tool_calls 时，有 DSML/XML 兜底解析

## 快速导航

| 我要… | 位置 |
|---|---|
| 换模型 | `agent/.env`：`LANGCHAIN_PROVIDER` + `LANGCHAIN_MODEL_NAME` + `<X>_API_KEY` |
| 加 provider | `src/providers/capabilities.py:_PROVIDERS` + `llm_providers.json` |
| 看支持的模型 | `vibe-trading provider doctor` |
| 改超时/重试 | `TIMEOUT_SECONDS` / `MAX_RETRIES` env |
| 改工具过滤 | `VIBE_TRADING_DENY_TOOL_PREFIXES`、`VIBE_TRADING_BASH_POLICY` |

## 详细说明

```
build_llm(provider, model) → LangChain BaseChatModel
  特殊分支：openai-codex / copilot / claude-cli / anthropic / deepseek
  其余：ChatOpenAIWithReasoning（OpenAI 兼容）

ChatLLM
  bind_tools(offered_tools(...))
  stream_chat() → LLMResponse
      归一化 chunk：text / reasoning / tool_calls
      + DSML/XML 兜底解析（模型把工具语法当散文输出时）
```

**超时与重试**：`supervised_pulls` 让每次 pull 与空闲超时/总超时/取消信号赛跑；失败抛 `ProviderStreamError(retryable, retry_after_s)`，循环重试一次并按 `Retry-After` 退避。

**上下文窗口**：`VIBE_TRADING_CONTEXT_WINDOW` > 从溢出错误学到的值 > `context_windows.json` > 128000。

### 加一个 OpenAI 兼容 provider

1. `capabilities.py` 的 `_PROVIDERS` 加条目（能力位：是否支持 tools / reasoning / vision）
2. `llm_providers.json` 加记录（`default_base_url`，Settings UI 会显示）
3. 设 `LANGCHAIN_PROVIDER=<name>`、`<NAME>_API_KEY`、可选 `<NAME>_BASE_URL`

非兼容的（需要自己的协议）再在 `build_llm` 加分支 + 仿 `claude_cli.py` 写 `BaseChatModel` 适配器。

## 陷阱

1. **`top_level_reasoning_effort` 是严格正整数白名单**：先设 False，等真跑通一次请求再开
2. `.env` 只加载第一个存在的候选文件，旧的 `~/.vibe-trading/.env` 会盖住 `agent/.env`
3. `agent/tests/test_llm_provider_defaults.py` 会校验 `llm_providers.json` 与 `_PROVIDERS` 一致，两处不同步会挂

## 测试

```bash
pytest agent/tests/test_llm_provider_defaults.py agent/tests/test_chat_llm_streaming.py -q
pytest agent/tests/test_provider_agnostic_tool_policy.py agent/tests/test_provider_endpoint_guard.py -q
```
