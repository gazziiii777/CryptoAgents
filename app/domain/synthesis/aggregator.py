import logging

from app.domain.models.analysis import (
    DerivativesReport,
    MacroReport,
    SentimentReport,
    SignalSynthesis,
    TechnicalReport,
)
from core.settings import settings

logger = logging.getLogger(__name__)

_BIAS_SCORE = {"Bullish": 1.0, "Bearish": -1.0, "Neutral": 0.0}
_DIRECTION_SCORE = {"Long": 1.0, "Short": -1.0, "No Signal": 0.0}

_WEIGHTS = {"macro": 0.20, "derivatives": 0.25, "sentiment": 0.20, "technical": 0.35}
_BIAS_THRESHOLD = 0.15


def _classify_bias(weighted_sum: float) -> str:
    if weighted_sum >= _BIAS_THRESHOLD:
        return "Bullish"
    if weighted_sum <= -_BIAS_THRESHOLD:
        return "Bearish"
    return "Neutral"


def _derive_risks(
    votes: dict[str, float],
    confluence_score: float,
    macro: MacroReport,
    technical: TechnicalReport,
) -> list[str]:
    risks: list[str] = []
    bulls = [name for name, vote in votes.items() if vote > 0]
    bears = [name for name, vote in votes.items() if vote < 0]
    if bulls and bears:
        risks.append(
            f"Analyst conflict: {', '.join(bulls)} bullish vs {', '.join(bears)} bearish"
        )
    if confluence_score < settings.CONFLUENCE_GATE:
        risks.append(
            f"Low confluence ({confluence_score:.2f} < {settings.CONFLUENCE_GATE})"
        )
    if not macro.alts_tradeable:
        risks.append("Macro: altcoins flagged not tradeable")
    if technical.signal_direction == "No Signal":
        risks.append("Technical: no clear setup")
    return risks


def aggregate_signals(
    macro: MacroReport,
    derivatives: DerivativesReport,
    sentiment: SentimentReport,
    technical: TechnicalReport,
) -> SignalSynthesis:
    """Детерминированная свёртка 4 отчётов в SignalSynthesis (взвешенное голосование).

    confluence_score = |взвешенная сумма голосов| × CONFIDENCE_SHRINKAGE.
    Шринкейдж (по умолчанию 0.75) корректирует системную overconfidence LLM:
    исследования (calibration papers) показывают, что выраженная уверенность
    моделей завышена. Гейт CONFLUENCE_GATE применяется уже к ужатому значению,
    поэтому проходят только действительно согласованные сетапы. Направление
    (overall_bias) считается по сырой сумме — шринкейдж влияет лишь на conviction.
    """
    votes = {
        "macro": _BIAS_SCORE[macro.btc_bias],
        "derivatives": _BIAS_SCORE[derivatives.overall_bias],
        "sentiment": _BIAS_SCORE[sentiment.overall_bias],
        "technical": _DIRECTION_SCORE[technical.signal_direction],
    }
    weighted_sum = sum(_WEIGHTS[name] * vote for name, vote in votes.items())
    overall_bias = _classify_bias(weighted_sum)
    confluence_score = abs(weighted_sum) * settings.CONFIDENCE_SHRINKAGE
    has_conflict = any(v > 0 for v in votes.values()) and any(
        v < 0 for v in votes.values()
    )
    risks = _derive_risks(votes, confluence_score, macro, technical)

    synthesis = SignalSynthesis(
        overall_bias=overall_bias,
        confluence_score=confluence_score,
        analyst_confluence=confluence_score,
        has_significant_conflict=has_conflict,
        scores_by_analyst=votes,
        top_risks=risks,
        reasoning=(
            f"Weighted vote {weighted_sum:+.2f} → {overall_bias}; "
            f"confluence {confluence_score:.2f}; "
            f"votes={votes}."
        ),
    )
    logger.info(
        "signal synthesis complete",
        extra={
            "overall_bias": overall_bias,
            "confluence_score": round(confluence_score, 3),
            "has_conflict": has_conflict,
        },
    )
    return synthesis
