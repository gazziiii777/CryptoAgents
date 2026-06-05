import pytest

from app.domain.synthesis.aggregator import aggregate_signals
from app.domain.models.analysis import (
    DerivativesReport,
    MacroReport,
    SentimentReport,
    TechnicalReport,
)
from core.settings import settings

_TECHNICAL_WEIGHT = 0.35


def _macro(btc_bias: str = "Bullish", alts_tradeable: bool = True) -> MacroReport:
    return MacroReport(
        reasoning="r",
        regime="Trending Up",
        btc_bias=btc_bias,
        dominance_trend="Flat",
        alts_tradeable=alts_tradeable,
    )


def _deriv(overall_bias: str = "Bullish") -> DerivativesReport:
    return DerivativesReport(
        key_insight="k",
        funding_signal="Neutral",
        oi_signal="Neutral",
        ls_signal="Balanced",
        liq_nearest_long=None,
        liq_nearest_short=None,
        cvd_direction="Neutral",
        overall_bias=overall_bias,
    )


def _senti(overall_bias: str = "Bullish") -> SentimentReport:
    return SentimentReport(
        key_insight="k",
        social_sentiment="Bullish",
        fear_greed_label="Neutral",
        news_sentiment="Neutral",
        overall_bias=overall_bias,
    )


def _tech(signal_direction: str = "Long") -> TechnicalReport:
    return TechnicalReport(
        market_structure="m",
        htf_bias="Bullish",
        setup_bias="Bullish",
        key_levels=[],
        entry_timeframe_note="n",
        signal_direction=signal_direction,
        confidence=0.6,
    )


def test_full_agreement_bullish_high_confluence() -> None:
    synth = aggregate_signals(
        macro=_macro(), derivatives=_deriv(), sentiment=_senti(), technical=_tech()
    )
    assert synth.overall_bias == "Bullish"
    assert synth.confluence_score == pytest.approx(settings.CONFIDENCE_SHRINKAGE)
    assert synth.analyst_confluence == pytest.approx(synth.confluence_score)
    assert synth.has_significant_conflict is False
    assert synth.top_risks == []
    assert set(synth.scores_by_analyst) == {
        "macro",
        "derivatives",
        "sentiment",
        "technical",
    }


def test_shrinkage_scales_confluence() -> None:
    """confluence = |weighted_sum| × CONFIDENCE_SHRINKAGE (один technical-голос)."""
    synth = aggregate_signals(
        macro=_macro(btc_bias="Neutral"),
        derivatives=_deriv(overall_bias="Neutral"),
        sentiment=_senti(overall_bias="Neutral"),
        technical=_tech(signal_direction="Long"),
    )
    expected = _TECHNICAL_WEIGHT * settings.CONFIDENCE_SHRINKAGE
    assert synth.confluence_score == pytest.approx(expected)


def test_conflict_flagged_and_confluence_low() -> None:
    synth = aggregate_signals(
        macro=_macro(btc_bias="Bullish"),
        derivatives=_deriv(overall_bias="Bearish"),
        sentiment=_senti(overall_bias="Neutral"),
        technical=_tech(signal_direction="No Signal"),
    )
    assert synth.has_significant_conflict is True
    assert synth.overall_bias == "Neutral"
    assert synth.confluence_score < settings.CONFLUENCE_GATE
    assert any("conflict" in r.lower() for r in synth.top_risks)


def test_all_neutral_zero_confluence() -> None:
    synth = aggregate_signals(
        macro=_macro(btc_bias="Neutral"),
        derivatives=_deriv(overall_bias="Neutral"),
        sentiment=_senti(overall_bias="Neutral"),
        technical=_tech(signal_direction="No Signal"),
    )
    assert synth.overall_bias == "Neutral"
    assert synth.confluence_score == pytest.approx(0.0)
