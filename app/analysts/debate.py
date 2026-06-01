import asyncio
import logging
from string import Template
from typing import Literal

from app.llm_gateway.service import LLMService
from app.models.analysis import (
    DerivativesReport,
    MacroReport,
    ResearchCase,
    SentimentReport,
    SignalSynthesis,
    TechnicalReport,
    TraderVerdict,
)
from core.prompts.loader import load_prompt
from core.settings import settings

logger = logging.getLogger(__name__)

_DISAGREEMENT_PENALTY = 0.5


def _reports_block(
    macro: MacroReport,
    derivatives: DerivativesReport,
    sentiment: SentimentReport,
    technical: TechnicalReport,
    synthesis: SignalSynthesis,
) -> str:
    """Сводка четырёх отчётов + синтеза одним блоком для bull/bear-промптов."""
    return (
        f"Market regime (risk-appetite CONTEXT, not a directional call on THIS asset): "
        f"regime={macro.regime}, btc_bias={macro.btc_bias}, "
        f"alts_tradeable={macro.alts_tradeable}. {macro.reasoning}\n"
        f"Derivatives: bias={derivatives.overall_bias}, "
        f"funding={derivatives.funding_signal}, oi={derivatives.oi_signal}, "
        f"cvd={derivatives.cvd_direction}. {derivatives.key_insight}\n"
        f"Sentiment: bias={sentiment.overall_bias}, "
        f"social={sentiment.social_sentiment}, fear_greed={sentiment.fear_greed_label}. "
        f"{sentiment.key_insight}\n"
        f"Technical: signal={technical.signal_direction}, htf={technical.htf_bias}, "
        f"setup={technical.setup_bias}, confidence={technical.confidence:.2f}. "
        f"{technical.market_structure}\n"
        f"Analyst synthesis: bias={synthesis.overall_bias}, "
        f"confluence={synthesis.confluence_score:.2f}."
    )


async def _research_case(
    service: LLMService, side: Literal["bull", "bear"], symbol: str, reports: str
) -> ResearchCase:
    prompt = load_prompt(side)
    return await service.structured(
        model=settings.LLM_QUICK_MODEL,
        system=prompt.system,
        user=Template(prompt.user).substitute(symbol=symbol, reports=reports),
        response_model=ResearchCase,
        entity_type=side,
    )


async def _trader_verdict(
    service: LLMService,
    symbol: str,
    bull: ResearchCase,
    bear: ResearchCase,
    synthesis: SignalSynthesis,
) -> TraderVerdict:
    prompt = load_prompt("trader")
    user = Template(prompt.user).substitute(
        symbol=symbol,
        synthesis_bias=synthesis.overall_bias,
        confluence=f"{synthesis.confluence_score:.2f}",
        bull_conviction=f"{bull.conviction:.2f}",
        bull_thesis=bull.thesis,
        bull_points="; ".join(bull.key_points) or "none",
        bear_conviction=f"{bear.conviction:.2f}",
        bear_thesis=bear.thesis,
        bear_points="; ".join(bear.key_points) or "none",
    )
    return await service.structured(
        model=settings.LLM_DEEP_MODEL,
        system=prompt.system,
        user=user,
        response_model=TraderVerdict,
        entity_type="trader",
    )


async def run_debate(
    service: LLMService,
    symbol: str,
    macro: MacroReport,
    derivatives: DerivativesReport,
    sentiment: SentimentReport,
    technical: TechnicalReport,
    synthesis: SignalSynthesis,
) -> tuple[ResearchCase, ResearchCase, TraderVerdict]:
    """Bull + Bear (параллельно) → Trader. Возвращает (bull, bear, verdict)."""
    reports = _reports_block(macro, derivatives, sentiment, technical, synthesis)
    bull, bear = await asyncio.gather(
        _research_case(service, "bull", symbol, reports),
        _research_case(service, "bear", symbol, reports),
    )
    verdict = await _trader_verdict(service, symbol, bull, bear, synthesis)
    logger.info(
        "debate complete",
        extra={
            "symbol": symbol,
            "verdict": verdict.verdict,
            "conviction": round(verdict.conviction, 3),
            "bull_conviction": round(bull.conviction, 3),
            "bear_conviction": round(bear.conviction, 3),
        },
    )
    return bull, bear, verdict


def apply_trader_verdict(
    synthesis: SignalSynthesis, verdict: TraderVerdict, shrinkage: float
) -> SignalSynthesis:
    """Накладывает вердикт трейдера на синтез.

    Трейдер — финальный решающий: его направление становится overall_bias, а
    confluence = conviction × shrinkage (та же коррекция overconfidence, что в
    аггрегаторе). При расхождении направления трейдера с голосованием аналитиков
    confluence дополнительно режется (_DISAGREEMENT_PENALTY) — голосование служит
    sanity-check. no_trade обнуляет confluence (гейт не пройдёт).
    """
    if verdict.verdict == "no_trade":
        return synthesis.model_copy(
            update={
                "overall_bias": "Neutral",
                "confluence_score": 0.0,
                "reasoning": f"Trader: no_trade. {verdict.reasoning}",
            }
        )
    bias = "Bullish" if verdict.verdict == "long" else "Bearish"
    conf = verdict.conviction * shrinkage
    if bias != synthesis.overall_bias:
        conf *= _DISAGREEMENT_PENALTY
    return synthesis.model_copy(
        update={
            "overall_bias": bias,
            "confluence_score": conf,
            "reasoning": f"Trader: {verdict.verdict} (conv {verdict.conviction:.2f}). "
            f"{verdict.reasoning}",
        }
    )
