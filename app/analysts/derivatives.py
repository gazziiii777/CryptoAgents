import logging
from string import Template
from typing import Literal

from app.models.analysis import DerivativesReport
from core.prompts.loader import load_prompt
from app.llm_gateway.service import LLMService
from app.models.screener import SignalDetails
from core.settings import settings

logger = logging.getLogger(__name__)

_ENTITY_TYPE = "derivatives"


def _ratio(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "n/a"


def classify_funding_squeeze_risk(
    funding_rate: float,
) -> Literal["high", "moderate", "none"]:
    """Контрарный риск сквиза по экстремальности funding.

    |rate| >= FUNDING_EXTREME_PCT → 'high' (толпа перегружена, вероятен каскад
    ликвидаций против неё, сигнал контрарный); >= FUNDING_RATE_HIGH → 'moderate';
    иначе 'none'. Знак funding'а (long/short squeeze) трактует LLM по prompt.
    """
    magnitude = abs(funding_rate)
    if magnitude >= settings.FUNDING_EXTREME_PCT:
        return "high"
    if magnitude >= settings.FUNDING_RATE_HIGH:
        return "moderate"
    return "none"


def _render_user_prompt(template: str, signals: SignalDetails) -> str:
    return Template(template).substitute(
        funding_rate=f"{signals.funding_rate:+.5f}",
        funding_bias=signals.funding_bias,
        oi_weighted_funding_bias=signals.oi_weighted_funding_bias,
        funding_squeeze_risk=classify_funding_squeeze_risk(signals.funding_rate),
        smart_money_divergence=signals.smart_money_divergence,
        oi_change_4h=f"{signals.oi_change_4h_pct * 100:+.2f}%",
        oi_trend=signals.oi_trend,
        oi_aggregated_trend=signals.oi_aggregated_trend,
        long_short_ratio=_ratio(signals.long_short_ratio),
        top_trader_ls_ratio=_ratio(signals.top_trader_ls_ratio),
        cvd_trend=signals.cvd_trend,
        cvd_price_divergence=signals.cvd_price_divergence or "n/a",
        liq_spike=str(signals.liq_spike),
        basis=f"{signals.basis:.4f}" if signals.basis is not None else "n/a",
    )


async def analyze_derivatives(
    service: LLMService, signals: SignalDetails
) -> DerivativesReport:
    """Derivatives-аналитик: SignalDetails → DerivativesReport (funding/OI/LS/CVD bias)."""
    prompt = load_prompt(_ENTITY_TYPE)
    report = await service.structured(
        model=settings.LLM_QUICK_MODEL,
        system=prompt.system,
        user=_render_user_prompt(prompt.user, signals),
        response_model=DerivativesReport,
        entity_type=_ENTITY_TYPE,
    )
    logger.info(
        "derivatives analysis complete",
        extra={"analyst": _ENTITY_TYPE, "result": report.model_dump(mode="json")},
    )
    return report
