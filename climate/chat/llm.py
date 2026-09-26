"""The LLM provider behind a small interface, so it can be swapped (and faked in tests)."""

from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import groq
from django.conf import settings

NOT_CONFIGURED = "The chat service isn't configured right now. The charts and API still work."


class LLMUnavailable(Exception):
    """The provider can't answer right now: no key, rate limited, timed out or down (HTTP 503)."""


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON text, exactly as the model produced it


@dataclass(frozen=True)
class LLMReply:
    content: str | None
    tool_calls: list[ToolCall]


class LLMClient(Protocol):
    model: str

    def complete(self, messages: list[dict], tools: list[dict]) -> LLMReply: ...


class GroqClient:
    """Groq chat completions (OpenAI-compatible) with tool calling.

    Groq's free tier limits tokens per minute per model, so a rate-limited call moves straight on
    to the next model in the chain (each has its own quota) instead of sleeping on Retry-After.
    """

    def __init__(
        self, api_key: str, model: str, timeout: float, fallback_models: tuple[str, ...] = ()
    ):
        if not api_key:
            raise LLMUnavailable(NOT_CONFIGURED)
        self.model = model  # the model that produced the latest reply
        self._models = [m for m in (model, *fallback_models) if m]
        self._client = _sdk(api_key, timeout)

    def complete(self, messages: list[dict], tools: list[dict]) -> LLMReply:
        for model in self._models:
            try:
                response = self._create(model, messages, tools)
            except groq.RateLimitError as exc:
                last_error = exc
                continue
            self.model = model
            break
        else:
            raise LLMUnavailable("The chat service is busy. Try again in a minute.") from last_error

        if not response.choices:
            raise LLMUnavailable("The chat service isn't available right now.")
        message = response.choices[0].message
        return LLMReply(
            content=message.content,
            tool_calls=[
                ToolCall(call.id, call.function.name, call.function.arguments)
                for call in message.tool_calls or []
            ],
        )

    def _create(self, model: str, messages: list[dict], tools: list[dict]):
        try:
            return self._client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.2,
                # Groq counts the requested budget against per-minute quotas (qwen's output
                # limit is 1,000 tokens a minute); answers are 1-3 sentences, well under this.
                max_completion_tokens=600,
            )
        except groq.RateLimitError:
            raise
        except groq.APITimeoutError as exc:
            raise LLMUnavailable("The chat service took too long to answer. Try again.") from exc
        except groq.APIError as exc:  # connection errors, auth, 5xx, malformed tool calls
            raise LLMUnavailable("The chat service isn't available right now.") from exc


@lru_cache(maxsize=4)
def _sdk(api_key: str, timeout: float) -> groq.Groq:
    """One SDK client (and HTTP connection pool) per key, reused across requests."""
    return groq.Groq(api_key=api_key, timeout=timeout, max_retries=0)


def default_client() -> LLMClient:
    return GroqClient(
        settings.GROQ_API_KEY,
        settings.LLM_MODEL,
        settings.LLM_TIMEOUT,
        fallback_models=tuple(settings.LLM_FALLBACK_MODELS),
    )
