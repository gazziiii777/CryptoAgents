from pydantic import BaseModel, ConfigDict, Field


class LLMUsage(BaseModel):
    """Учёт одного LLM-вызова — пишется в Event(event_type='llm_call').payload_json.

    cost_usd — оценка стоимости из прайс-карты litellm (производная метрика, не баланс),
    поэтому float, а не Decimal. Агрегируется в дневной бюджет и позже в llm_cost_24h.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    model: str = Field(description="Идентификатор модели, как ушёл в litellm")
    prompt_tokens: int = Field(ge=0, description="Токены входа")
    completion_tokens: int = Field(ge=0, description="Токены выхода")
    total_tokens: int = Field(ge=0, description="Суммарные токены")
    cost_usd: float = Field(ge=0.0, description="Оценка стоимости вызова в USD")
    latency_ms: int = Field(ge=0, description="Латентность вызова в миллисекундах")
