import logging
from string import Template

from app.models.analysis import MacroReport
from core.prompts.loader import load_prompt
from app.clients.coingecko.models import MacroSnapshot
from app.llm_gateway.service import LLMService
from core.settings import settings

logger = logging.getLogger(__name__)

_ENTITY_TYPE = "macro"


def _render_user_prompt(
    template: str, macro: MacroSnapshot, fear_greed: int | None
) -> str:
    return Template(template).substitute(
        btc_price=f"${macro.btc_price_usd:,.0f}",
        btc_change_24h=f"{macro.btc_change_24h:+.2f}%",
        btc_change_7d=f"{macro.btc_change_7d:+.2f}%",
        btc_dominance=f"{macro.btc_dominance:.2f}%",
        total_mc_change=f"{macro.total_market_cap_change_24h:+.2f}%",
        fear_greed=str(fear_greed) if fear_greed is not None else "n/a",
    )


async def analyze_macro(
    service: LLMService, macro: MacroSnapshot, fear_greed: int | None = None
) -> MacroReport:
    """Макро-аналитик: market snapshot → MacroReport (regime, BTC bias, alts tradeable)."""
    prompt = load_prompt(_ENTITY_TYPE)
    report = await service.structured(
        model=settings.LLM_QUICK_MODEL,
        system=prompt.system,
        user=_render_user_prompt(prompt.user, macro, fear_greed),
        response_model=MacroReport,
        entity_type=_ENTITY_TYPE,
    )
    logger.info(
        "macro analysis complete",
        extra={"analyst": _ENTITY_TYPE, "result": report.model_dump(mode="json")},
    )
    return report
