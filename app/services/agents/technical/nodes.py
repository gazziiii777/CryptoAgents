import logging
from string import Template

from app.domain.models.analysis import TechnicalReport
from core.prompts.loader import load_prompt
from app.services.agents.technical.levels import compute_facts
from app.services.agents.technical.models import TechnicalFacts
from app.services.agents.technical.state import TechnicalState
from app.llm_gateway.service import LLMService
from core.settings import settings

logger = logging.getLogger(__name__)

_ENTITY_TYPE = "technical"


def _price(value: float) -> str:
    return f"{value:.6g}"


def _render_user_prompt(template: str, symbol: str, facts: TechnicalFacts) -> str:
    return Template(template).substitute(
        symbol=symbol,
        current_price=_price(facts.current_price),
        atr=_price(facts.atr),
        ema_20=_price(facts.ema_20),
        ema_50=_price(facts.ema_50),
        recent_high=_price(facts.recent_high),
        recent_low=_price(facts.recent_low),
        prev_day_high=_price(facts.prev_day_high),
        prev_day_low=_price(facts.prev_day_low),
        adx=f"{facts.adx:.1f}",
        rsi=f"{facts.rsi:.1f}" if facts.rsi is not None else "n/a",
        rsi_divergence=facts.rsi_divergence or "none",
        macd=facts.macd or "neutral",
        ema_cross=facts.ema_cross or "none",
        daily_trend=facts.daily_trend,
    )


def compute_levels_node(state: TechnicalState) -> dict[str, TechnicalFacts]:
    """Нода 1: детерминированный расчёт уровней из свечей."""
    return {"facts": compute_facts(state.candles_4h, state.candles_1d)}


async def interpret_node(
    state: TechnicalState, *, service: LLMService
) -> dict[str, TechnicalReport]:
    """Нода 2: LLM интерпретирует уровни → TechnicalReport (deep-модель)."""
    if state.facts is None:
        raise RuntimeError("interpret_node reached before compute_levels_node")
    prompt = load_prompt(_ENTITY_TYPE)
    report = await service.structured(
        model=settings.LLM_DEEP_MODEL,
        system=prompt.system,
        user=_render_user_prompt(prompt.user, state.symbol, state.facts),
        response_model=TechnicalReport,
        entity_type=_ENTITY_TYPE,
    )
    logger.info(
        "technical analysis complete",
        extra={
            "analyst": _ENTITY_TYPE,
            "symbol": state.symbol,
            "result": report.model_dump(mode="json"),
        },
    )
    return {"report": report}
