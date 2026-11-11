"""LLM Adapter：內部統一格式 ↔ 各家 API。Agent loop 只認這個介面，換模型不動其他程式。

- anthropic：Anthropic 官方 SDK（Claude API、或接入方的 Foundry／相容閘道 base_url）
- openai_compatible：Chat Completions function calling（Azure OpenAI、vLLM、Ollama、LiteLLM…）
"""

import base64
import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.config import settings


@dataclass
class ToolSpec:
    name: str
    description: str
    schema: dict


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class Usage:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0

    def add(self, o: "Usage") -> None:
        self.input += o.input
        self.output += o.output
        self.cache_read += o.cache_read
        self.cache_write += o.cache_write


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCall]
    assistant_message: Any  # 原生格式，原封不動放回對話
    usage: Usage
    stop_reason: str
    model: str
    extra: dict = field(default_factory=dict)


class LLMClient(Protocol):
    provider: str

    def chat(self, model: str, system_static: str, system_dynamic: str, messages: list, tools: list[ToolSpec],
             effort: str, max_tokens: int = 4096) -> LLMResponse: ...

    def user(self, text: str) -> Any: ...

    def image_user(self, text: str, image: bytes, media_type: str) -> Any: ...

    def assistant_text(self, text: str) -> Any: ...

    def system_note(self, text: str) -> Any: ...

    def tool_results(self, results: list[tuple[ToolCall, str, bool]]) -> list: ...


class AnthropicClient:
    provider = "anthropic"

    def __init__(self) -> None:
        import anthropic

        self._sdk = anthropic
        self.client = anthropic.Anthropic(api_key=settings.llm_api_key, base_url=settings.llm_base_url or None)
        # server-side fallback 只有官方 Claude API 支援；接入方走自己的閘道時關閉
        self.fallbacks = settings.llm_anthropic_fallbacks and not settings.llm_base_url

    def chat(self, model, system_static, system_dynamic, messages, tools, effort, max_tokens=4096) -> LLMResponse:
        tool_defs = [{"name": t.name, "description": t.description, "input_schema": t.schema} for t in tools]
        if tool_defs:
            tool_defs[-1]["cache_control"] = {"type": "ephemeral"}  # tools＋固定 system 一起進快取
        system = [{"type": "text", "text": system_static, "cache_control": {"type": "ephemeral"}}]
        if system_dynamic:
            system.append({"type": "text", "text": system_dynamic})
        kwargs = dict(model=model, max_tokens=max_tokens, system=system, messages=messages,
                      output_config={"effort": effort})
        if tool_defs:
            kwargs["tools"] = tool_defs
        if self.fallbacks and not model.startswith("claude-haiku"):
            r = self.client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
        else:
            r = self.client.messages.create(**kwargs)
        text = "".join(b.text for b in r.content if b.type == "text")
        calls = [ToolCall(b.id, b.name, dict(b.input)) for b in r.content if b.type == "tool_use"]
        u = r.usage
        usage = Usage(u.input_tokens, u.output_tokens, u.cache_read_input_tokens or 0, u.cache_creation_input_tokens or 0)
        return LLMResponse(text, calls, {"role": "assistant", "content": r.content}, usage, r.stop_reason or "", r.model)

    def user(self, text: str) -> dict:
        return {"role": "user", "content": text}

    def image_user(self, text: str, image: bytes, media_type: str) -> dict:
        data = base64.b64encode(image).decode()
        return {"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
            {"type": "text", "text": text}]}

    def assistant_text(self, text: str) -> dict:
        return {"role": "assistant", "content": text}

    def system_note(self, text: str) -> dict:
        # Claude 5.5 系列支援對話中的 system 訊息（須接在 user 訊息之後）
        return {"role": "system", "content": text}

    def tool_results(self, results) -> list:
        # 平行工具呼叫的結果必須放在同一則 user 訊息
        return [{"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": c.id, "content": out, "is_error": err} for c, out, err in results]}]


class FoundryClient(AnthropicClient):
    """Microsoft Foundry 上的 Claude：用官方的 AnthropicFoundry client；模型名稱填部署名稱。"""

    provider = "foundry"

    def __init__(self) -> None:
        import anthropic

        self.client = anthropic.AnthropicFoundry(api_key=settings.llm_api_key, resource=settings.llm_foundry_resource,
                                                 base_url=settings.llm_base_url or None)
        self.fallbacks = False  # server-side fallback 只有官方 Claude API 支援


_THINK = re.compile(r"<think>.*?</think>", re.S)


class OpenAICompatibleClient:
    provider = "openai_compatible"

    def __init__(self) -> None:
        import openai

        self.client = openai.OpenAI(api_key=settings.llm_api_key or "not-needed", base_url=settings.llm_base_url)

    def chat(self, model, system_static, system_dynamic, messages, tools, effort, max_tokens=4096) -> LLMResponse:
        tool_defs = [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.schema}}
                     for t in tools]
        msgs = [{"role": "system", "content": "\n\n".join(s for s in (system_static, system_dynamic) if s)}] + messages
        kwargs = dict(model=model, messages=msgs, max_tokens=max_tokens)
        if settings.llm_reasoning_effort:
            kwargs["reasoning_effort"] = settings.llm_reasoning_effort  # 例：Ollama 推理模型設 none，避免 token 全耗在思考
        if tool_defs:
            kwargs["tools"] = tool_defs
        r = self.client.chat.completions.create(**kwargs)
        m = r.choices[0].message
        calls = []
        for tc in m.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"__invalid_json__": tc.function.arguments}
            calls.append(ToolCall(tc.id, tc.function.name, args))
        text = _THINK.sub("", m.content or "").strip()
        assistant = {"role": "assistant", "content": m.content or ""}
        if m.tool_calls:
            assistant["tool_calls"] = [{"id": tc.id, "type": "function",
                                        "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                                       for tc in m.tool_calls]
        u = r.usage
        cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0 if u else 0
        usage = Usage((u.prompt_tokens - cached) if u else 0, u.completion_tokens if u else 0, cached, 0)
        return LLMResponse(text, calls, assistant, usage, r.choices[0].finish_reason or "", r.model or model)

    def user(self, text: str) -> dict:
        return {"role": "user", "content": text}

    def image_user(self, text: str, image: bytes, media_type: str) -> dict:
        url = f"data:{media_type};base64,{base64.b64encode(image).decode()}"
        return {"role": "user", "content": [{"type": "text", "text": text}, {"type": "image_url", "image_url": {"url": url}}]}

    def assistant_text(self, text: str) -> dict:
        return {"role": "assistant", "content": text}

    def system_note(self, text: str) -> dict:
        # 開源模型（例如 Ollama 的 qwen）常忽略對話中途的 system 訊息，改用 user 角色並標明是系統提示
        return {"role": "user", "content": f"（系統提示，非使用者發言）{text}"}

    def tool_results(self, results) -> list:
        return [{"role": "tool", "tool_call_id": c.id, "content": out} for c, out, _ in results]


PROVIDERS = {"anthropic": AnthropicClient, "foundry": FoundryClient, "openai_compatible": OpenAICompatibleClient}
_client: LLMClient | None = None


def not_configured() -> str | None:
    """模型設定缺了什麼；回傳 None 代表可以用。"""
    p = settings.llm_provider
    if p not in PROVIDERS:
        return f"不支援的 LLM_PROVIDER「{p}」，可用：{'、'.join(PROVIDERS)}"
    if p in ("anthropic", "foundry") and not settings.llm_api_key:
        return "尚未設定 LLM_API_KEY"
    if p == "foundry" and not (settings.llm_foundry_resource or settings.llm_base_url):
        return "Foundry 需要設定 LLM_FOUNDRY_RESOURCE（或 LLM_BASE_URL）"
    if p == "openai_compatible" and not settings.llm_base_url:
        return "openai_compatible 需要設定 LLM_BASE_URL"
    return None


def get_client() -> LLMClient:
    global _client
    if _client is None:
        _client = PROVIDERS[settings.llm_provider]()
    return _client
