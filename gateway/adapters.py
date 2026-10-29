"""Model adapter contract and first concrete adapters.

Implements the adapter contract described in docs/model-gateway-architecture.md section 2.
"""

import json
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator

CHAT = "chat"
COMPLETION = "completion"
EMBEDDING = "embedding"
VISION = "vision"
TOOLS = "tools"
JSON_MODE = "json_mode"
STREAMING = "streaming"
CANCELLATION = "cancellation"

TOKEN_CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class Deployment:
    model: str
    version: str
    context_window: int
    capabilities: frozenset


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    source: str  # "model" when the runtime reported it, "estimated" otherwise


@dataclass(frozen=True)
class GenerateRequest:
    model: str
    messages: list
    max_output_tokens: int
    stream: bool = False


def estimate_tokens(text) -> int:
    """Char/4 estimate used only until a pinned tokenizer adapter is available."""
    if not text:
        return 0
    if not isinstance(text, str):
        text = str(text)
    return max(1, math.ceil(len(text) / TOKEN_CHARS_PER_TOKEN))


def message_text(message) -> str:
    content = message.get("content") if isinstance(message, dict) else message
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        return "\n".join(parts)
    return str(content)


class Adapter(ABC):
    """Contract every model host adapter must implement."""

    @abstractmethod
    def describe(self) -> Deployment:
        """Return deployment metadata: model, version/digest, context, capabilities."""

    @abstractmethod
    def count_input(self, messages: list) -> int:
        """Count input tokens for the full effective request (system, tools, history)."""

    @abstractmethod
    def generate(self, request: GenerateRequest, cancellation=None) -> Iterator[dict]:
        """Run inference and yield normalized result events."""

    @abstractmethod
    def cancel(self, request_id: str) -> bool:
        """Cancel an in-flight generation, if supported."""

    @abstractmethod
    def normalize_usage(self, result) -> Usage:
        """Normalize runtime usage into authoritative or estimated token counts."""

    @abstractmethod
    def health(self) -> dict:
        """Report host health for the gateway's checks."""


class OpenAICompatibleAdapter(Adapter):
    """Adapter for OpenAI-compatible servers (vLLM, llama.cpp server)."""

    def __init__(self, adapter_id, base_url, api_key, model, version="1", context_window=4096, capabilities=frozenset({CHAT, COMPLETION, STREAMING, CANCELLATION})):
        self.adapter_id = adapter_id
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.version = version
        self.context_window = context_window
        self.capabilities = frozenset(capabilities)

    def describe(self) -> Deployment:
        return Deployment(model=self.model, version=self.version, context_window=self.context_window, capabilities=self.capabilities)

    def count_input(self, messages: list) -> int:
        total = 0
        for message in messages or []:
            if not isinstance(message, dict):
                continue
            if message.get("role") == "tool":
                continue
            total += estimate_tokens(message_text(message))
        return total

    def generate(self, request: GenerateRequest, cancellation=None) -> Iterator[dict]:
        import httpx

        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": request.model,
            "messages": request.messages,
            "max_tokens": request.max_output_tokens,
        }
        if request.stream:
            events = []
            with httpx.Client() as client:
                with client.stream("POST", url, json=payload, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=30.0) as response:
                    if response.status_code != 200:
                        raise errors.GatewayError("model_error", f"Upstream chat completion failed with status {response.status_code}.")
                    final = {}
                    for line in response.iter_lines():
                        stripped = line.strip()
                        if not stripped.startswith("data:"):
                            continue
                        data_str = stripped[len("data:"):].strip()
                        if data_str == "[DONE]":
                            continue
                        data = json.loads(data_str)
                        delta = (data.get("choices") or [{}])[0].get("delta") or {}
                        content = delta.get("content") or ""
                        if content:
                            events.append({"type": "token", "text": content})
                        final = data
            done_content = "".join(event["text"] for event in events)
            usage = final.get("usage") or {}
            events.append({
                "type": "done",
                "content": done_content,
                "finish_reason": (final.get("choices") or [{}])[0].get("finish_reason") or "stop",
                "usage": {"prompt_tokens": usage.get("prompt_tokens") or 0, "completion_tokens": usage.get("completion_tokens") or 0},
            })
            return iter(events)
        response = httpx.post(url, json=payload, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=30.0)
        if response.status_code != 200:
            from gateway import errors

            raise errors.GatewayError("model_error", f"Upstream chat completion failed with status {response.status_code}.")
        data = response.json()
        return iter([{
            "content": (data.get("choices") or [{}])[0].get("message", {}).get("content") or "",
            "finish_reason": (data.get("choices") or [{}])[0].get("finish_reason") or "stop",
            "usage": {
                "prompt_tokens": (data.get("usage") or {}).get("prompt_tokens") or 0,
                "completion_tokens": (data.get("usage") or {}).get("completion_tokens") or 0,
            },
        }])

    def normalize_usage(self, result) -> Usage:
        usage = result.get("usage") or {}
        input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
        output_tokens = usage.get("completion_tokens") or usage.get("output_tokens") or 0
        source = "model" if (input_tokens or output_tokens) else "estimated"
        return Usage(input_tokens=input_tokens, output_tokens=output_tokens, source=source)

    def cancel(self, request_id: str) -> bool:
        return False

    def health(self) -> dict:
        import httpx

        try:
            response = httpx.get(f"{self.base_url}/models", headers={"Authorization": f"Bearer {self.api_key}"}, timeout=5.0)
            return {"status": "healthy" if response.status_code == 200 else "unhealthy"}
        except Exception:
            return {"status": "unhealthy"}


class OllamaAdapter(OpenAICompatibleAdapter):
    """Adapter for the Ollama chat endpoint, normalizing prompt/eval counts."""

    def __init__(self, adapter_id, base_url, api_key, model, version="1", context_window=4096, capabilities=frozenset({CHAT, STREAMING, CANCELLATION})):
        super().__init__(adapter_id, base_url, api_key, model, version=version, context_window=context_window, capabilities=capabilities | frozenset({CHAT}))

    def generate(self, request: GenerateRequest, cancellation=None) -> Iterator[dict]:
        import httpx

        from gateway import errors

        if request.stream:
            events = []
            with httpx.Client() as client:
                with client.stream(
                    "POST",
                    f"{self.base_url.rstrip('/')}/api/chat",
                    json={
                        "model": request.model,
                        "messages": request.messages,
                        "options": {"num_predict": request.max_output_tokens},
                    },
                    timeout=30.0,
                ) as response:
                    if response.status_code != 200:
                        raise errors.GatewayError("model_error", f"Ollama chat failed with status {response.status_code}.")
                    final = {}
                    for line in response.iter_lines():
                        stripped = line.strip()
                        if not stripped.startswith("data:"):
                            continue
                        data_str = stripped[len("data:"):].strip()
                        if not data_str:
                            continue
                        data = json.loads(data_str)
                        final = data
                        content = (data.get("message") or {}).get("content") or ""
                        if content:
                            events.append({"type": "token", "text": content})
                    done_content = "".join(event["text"] for event in events)
                    usage = final.get("usage") or {}
                    events.append({
                        "type": "done",
                        "content": done_content,
                        "finish_reason": "stop",
                        "usage": {
                            "prompt_tokens": usage.get("prompt_eval_count") or 0,
                            "completion_tokens": usage.get("eval_count") or 0,
                        },
                    })
            return iter(events)
        response = httpx.post(
            f"{self.base_url.rstrip('/')}/api/chat",
            json={
                "model": request.model,
                "messages": request.messages,
                "options": {"num_predict": request.max_output_tokens},
            },
            timeout=30.0,
        )
        if response.status_code != 200:
            raise errors.GatewayError("model_error", f"Ollama chat failed with status {response.status_code}.")
        data = response.json()
        message = data.get("message") or {}
        usage = data.get("usage") or {}
        return iter([{
            "content": message.get("content") or "",
            "finish_reason": "stop",
            "usage": {
                "prompt_tokens": usage.get("prompt_eval_count") or 0,
                "completion_tokens": usage.get("eval_count") or 0,
            },
        }])

    def normalize_usage(self, result) -> Usage:
        usage = result.get("usage") or {}
        input_tokens = usage.get("prompt_eval_count") or usage.get("prompt_tokens") or usage.get("input_tokens") or 0
        output_tokens = usage.get("eval_count") or usage.get("completion_tokens") or usage.get("output_tokens") or 0
        source = "model" if (input_tokens or output_tokens) else "estimated"
        return Usage(input_tokens=input_tokens, output_tokens=output_tokens, source=source)
