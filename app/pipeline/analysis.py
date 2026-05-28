import asyncio
import logging
from datetime import datetime, timezone
from typing import Literal

from app.aggregator import aggregate_signals
from app.agents.setup.graph import build_setup
from app.agents.technical.graph import analyze_technical
from app.analysts.debate import apply_trader_verdict, run_debate
from app.analysts.derivatives import analyze_derivatives, classify_funding_squeeze_risk
from app.analysts.devils_advocate import apply_devils_advocate, run_devils_advocate
from app.analysts.macro import analyze_macro
from app.analysts.sentiment import analyze_sentiment
from app.clients.ccxt.client import CcxtClient
from app.clients.ccxt.models import OHLCVCandle
from app.levelcomputer import resolve_setup
from app.llm_gateway.service import LLMService
from app.screener.indicators import calc_atr
from app.models.analysis import (
    CandidateSignal,
    DevilsAdvocateReport,
    MacroReport,
    ResearchCase,
    SignalSynthesis,
    TechnicalReport,
    TraderVerdict,
)
from app.models.enricher import EnrichedCandidate, EnrichmentResult
from app.models.setup import CryptoSetup, FinalSignal, SetupIntent
from app.riskvalidator import validate_risk
from app.signalformatter import format_signal
from core.constants.decisions import (
    REASON_DEVILS_VETO,
    REASON_LEVEL_FAILED,
    REASON_LOW_CONFLUENCE,
    REASON_NEUTRAL,
    REASON_NO_SETUP,
    REASON_RISK_PREFIX,
    REASON_SIGNAL_READY,
)
from core.constants.time import MS_PER_SECOND
from core.settings import settings

logger = logging.getLogger(__name__)

_SETUP_RESOLVE_ATTEMPTS = 2
_RESOLVE_CORRECTION = (
    "Your previous setup did not resolve to a valid, fillable trade: the entry was too "
    "far from the current price. Use entry.kind='market' to enter at the current price "
    "(this trend has no nearby pullback), keep the stop 0.3-5% away, and ensure the "
    "target is beyond entry with reward:risk >= 1.5."
)


def _manipulation_context(candidate: EnrichedCandidate) -> str:
    """Сводка manipulation-сигналов для Devil's Advocate."""
    signals = candidate.screener.signals
    return (
        f"- smart_money_divergence: {signals.smart_money_divergence}\n"
        f"- funding_squeeze_risk: {classify_funding_squeeze_risk(signals.funding_rate)}"
        f" (funding {signals.funding_rate:+.4f})\n"
        f"- pump_risk: {candidate.social.pump_risk}\n"
        f"- recent liquidation spike: {signals.liq_spike}"
    )


async def _run_setup_chain(
    service: LLMService,
    synthesis: SignalSynthesis,
    technical: TechnicalReport,
    candidate: EnrichedCandidate,
    candles_4h: list[OHLCVCandle],
    candles_1d: list[OHLCVCandle],
) -> tuple[
    SetupIntent | None,
    CryptoSetup | None,
    FinalSignal | None,
    str,
    DevilsAdvocateReport | None,
]:
    """Гейт → SetupBuilder → LevelComputer → RiskValidator → Devil's Advocate → FinalSignal.

    Возвращает (intent, crypto_setup, final_signal, reason, devils_advocate).
    Devil's Advocate — финальный veto: на готовом сетапе ищет critical-риски, корректирует
    confluence; если та падает ниже гейта — сетап отклоняется (REASON_DEVILS_VETO).
    """
    if synthesis.confluence_score < settings.CONFLUENCE_GATE:
        return None, None, None, REASON_LOW_CONFLUENCE, None
    if synthesis.overall_bias == "Neutral":
        return None, None, None, REASON_NEUTRAL, None

    direction: Literal["long", "short"] = (
        "long" if synthesis.overall_bias == "Bullish" else "short"
    )
    current_price = candles_4h[-1].close
    atr = calc_atr(candles_4h)
    funding_rate = candidate.screener.signals.funding_rate

    intent: SetupIntent | None = None
    setup: CryptoSetup | None = None
    correction: str | None = None
    for _ in range(_SETUP_RESOLVE_ATTEMPTS):
        intent = await build_setup(
            service, direction, technical, current_price, atr, correction=correction
        )
        if intent is None:
            return None, None, None, REASON_NO_SETUP, None
        setup = resolve_setup(
            intent, candles_4h, candles_1d, current_price, funding_rate
        )
        if setup is not None:
            break
        correction = _RESOLVE_CORRECTION
    if setup is None:
        return intent, None, None, REASON_LEVEL_FAILED, None

    risk_reason = validate_risk(setup)
    if risk_reason is not None:
        return intent, setup, None, f"{REASON_RISK_PREFIX}{risk_reason}", None

    da_report = await run_devils_advocate(
        service, candidate.symbol, synthesis, setup, _manipulation_context(candidate)
    )
    adjusted = apply_devils_advocate(synthesis, da_report)
    if adjusted.confluence_score < settings.CONFLUENCE_GATE:
        return intent, setup, None, REASON_DEVILS_VETO, da_report

    final = format_signal(candidate.symbol, adjusted, setup)
    return intent, setup, final, REASON_SIGNAL_READY, da_report


async def _analyze_candidate(
    service: LLMService,
    ccxt: CcxtClient,
    candidate: EnrichedCandidate,
    macro: MacroReport,
    fear_greed: int | None,
) -> CandidateSignal | None:
    """Полный анализ одного кандидата → CandidateSignal. None, если нет свечей."""
    derivatives = await analyze_derivatives(service, candidate.screener.signals)
    sentiment = await analyze_sentiment(service, candidate.social, fear_greed)
    candles_4h, candles_1d = await asyncio.gather(
        ccxt.fetch_ohlcv(
            candidate.symbol, timeframe="4h", limit=settings.SCREENER_4H_LIMIT
        ),
        ccxt.fetch_ohlcv(
            candidate.symbol, timeframe="1d", limit=settings.SCREENER_1D_LIMIT
        ),
    )
    if not candles_4h or not candles_1d:
        logger.warning("no candles for %s, skipping candidate", candidate.symbol)
        return None

    technical = await analyze_technical(
        service, candidate.symbol, candles_4h, candles_1d
    )
    synthesis = aggregate_signals(macro, derivatives, sentiment, technical)

    bull: ResearchCase | None = None
    bear: ResearchCase | None = None
    verdict: TraderVerdict | None = None
    if synthesis.overall_bias != "Neutral":
        bull, bear, verdict = await run_debate(
            service,
            candidate.symbol,
            macro,
            derivatives,
            sentiment,
            technical,
            synthesis,
        )
        synthesis = apply_trader_verdict(
            synthesis, verdict, settings.CONFIDENCE_SHRINKAGE
        )

    intent, setup, final, reason, da_report = await _run_setup_chain(
        service, synthesis, technical, candidate, candles_4h, candles_1d
    )
    bar_close_ts = datetime.fromtimestamp(
        candles_4h[-1].timestamp / MS_PER_SECOND, tz=timezone.utc
    )
    return CandidateSignal(
        candidate=candidate,
        macro=macro,
        derivatives=derivatives,
        sentiment=sentiment,
        technical=technical,
        synthesis=synthesis,
        bar_close_ts=bar_close_ts,
        bull_case=bull,
        bear_case=bear,
        trader_verdict=verdict,
        devils_advocate=da_report,
        setup_intent=intent,
        crypto_setup=setup,
        final_signal=final,
        decision_reason=reason,
    )


async def run_analysis(
    service: LLMService, enrichment: EnrichmentResult
) -> list[CandidateSignal]:
    """Прогоняет 4 аналитиков + setup-цепочку по каждому кандидату.

    Macro считается один раз на прогон. Сбой по одному кандидату логируется и не
    роняет остальной прогон (изоляция).
    """
    macro = await analyze_macro(service, enrichment.macro, enrichment.fear_greed)

    results: list[CandidateSignal] = []
    async with CcxtClient() as ccxt:
        for candidate in enrichment.candidates:
            try:
                candidate_signal = await _analyze_candidate(
                    service, ccxt, candidate, macro, enrichment.fear_greed
                )
            except Exception:
                logger.error(
                    "candidate analysis failed for %s", candidate.symbol, exc_info=True
                )
                continue
            if candidate_signal is None:
                continue
            results.append(candidate_signal)
            logger.info(
                "candidate synthesized",
                extra={
                    "symbol": candidate.symbol,
                    "overall_bias": candidate_signal.synthesis.overall_bias,
                    "confluence_score": round(
                        candidate_signal.synthesis.confluence_score, 3
                    ),
                    "decision_reason": candidate_signal.decision_reason,
                },
            )

    return results
