import logging
import time
from typing import TypeVar

import instructor
from instructor.core import InstructorError
from litellm import acompletion, completion_cost
from openai import OpenAIError
from pydantic import BaseModel, ValidationError

from app.clients.llm.exceptions import LLMCompletionError
from app.clients.llm.models import LLMUsage
from core.settings import settings
from core.constants.time import MS_PER_SECOND

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_COMPLETION_FAILURES = (InstructorError, OpenAIError, ValidationError)


def _route_model(model: str) -> str:
    """Префикс провайдера для litellm-роутинга claude-моделей без явного провайдера.

    settings хранит короткие имена (claude-haiku-4-5); litellm надёжно роутит их в
    Anthropic с префиксом anthropic/. Модели с уже указанным провайдером (openai/…,
    gpt-…) пропускаются без изменений.
    """
    if "/" in model or not model.startswith("claude"):
        return model
    return f"anthropic/{model}"


def _api_key_for(model: str) -> str | None:
    if model.startswith(("anthropic/", "claude")):
        return settings.ANTHROPIC_API_KEY or None
    if model.startswith(("openai/", "gpt")):
        return settings.OPENAI_API_KEY or None
    return None


def _extract_cost(raw: object) -> float:
    """Стоимость вызова из litellm: hidden response_cost, иначе пересчёт по прайс-карте.

    Для свежих моделей прайс-карта litellm может не содержать цену — тогда 0.0 с warning,
    бюджет на таком вызове не растёт (известное ограничение, не молчаливое проглатывание).
    """
    hidden = getattr(raw, "_hidden_params", None)
    if isinstance(hidden, dict):
        cost = hidden.get("response_cost")
        if cost is not None:
            return float(cost)
    try:
        return float(completion_cost(completion_response=raw))
    except Exception as exc:
        logger.warning("LLM cost unavailable (model pricing missing?): %s", exc)
        return 0.0


class LLMClient:
    """Тонкая обёртка instructor + litellm для structured-output вызовов.

    Возвращает распарсенную Pydantic-модель и LLMUsage (токены, стоимость, латентность).
    БД не трогает: budget gate и запись Event(llm_call) живут в LLMService.
    """

    def __init__(self) -> None:
        self._client = instructor.from_litellm(acompletion)

    async def complete(
        self,
        *,
        model: str,
        system: str,
        user: str,
        response_model: type[T],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> tuple[T, LLMUsage]:
        routed = _route_model(model)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        started = time.perf_counter()
        try:
            parsed, raw = await self._client.chat.completions.create_with_completion(
                model=routed,
                messages=messages,
                response_model=response_model,
                max_tokens=max_tokens or settings.LLM_MAX_OUTPUT_TOKENS,
                temperature=(
                    temperature if temperature is not None else settings.LLM_TEMPERATURE
                ),
                max_retries=settings.LLM_MAX_RETRIES,
                api_key=_api_key_for(routed),
                timeout=settings.LLM_TIMEOUT_S,
            )
        except _COMPLETION_FAILURES as exc:
            logger.error("LLM completion failed model=%s: %s", routed, exc)
            raise LLMCompletionError(
                f"LLM completion failed for {routed}: {exc}"
            ) from exc

        latency_ms = int((time.perf_counter() - started) * MS_PER_SECOND)
        usage = self._build_usage(routed, raw, latency_ms)
        logger.info(
            "LLM call ok model=%s tokens=%d cost_usd=%.5f latency_ms=%d",
            usage.model,
            usage.total_tokens,
            usage.cost_usd,
            usage.latency_ms,
        )
        return parsed, usage

    @staticmethod
    def _build_usage(model: str, raw: object, latency_ms: int) -> LLMUsage:
        usage_obj = getattr(raw, "usage", None)
        prompt_tokens = int(getattr(usage_obj, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage_obj, "completion_tokens", 0) or 0)
        total_tokens = int(getattr(usage_obj, "total_tokens", 0) or 0) or (
            prompt_tokens + completion_tokens
        )
        return LLMUsage(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=_extract_cost(raw),
            latency_ms=latency_ms,
        )
