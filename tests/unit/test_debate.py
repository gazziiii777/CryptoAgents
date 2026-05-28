import pytest

from app.analysts.debate import apply_trader_verdict, run_debate
from app.models.analysis import (
    DerivativesReport,
    MacroReport,
    ResearchCase,
    SentimentReport,
    SignalSynthesis,
    TechnicalReport,
    TraderVerdict,
)

_SHRINK = 0.75


def _synthesis(bias: str = "Bullish", confluence: float = 0.6) -> SignalSynthesis:
    return SignalSynthesis(
        overall_bias=bias,
        confluence_score=confluence,
        has_significant_conflict=False,
        scores_by_analyst={"macro": 1.0},
        top_risks=[],
        reasoning="prior",
    )


def _verdict(verdict: str = "long", conviction: float = 0.8) -> TraderVerdict:
    return TraderVerdict(verdict=verdict, conviction=conviction, reasoning="r")


def test_no_trade_zeroes_confluence():
    out = apply_trader_verdict(_synthesis(), _verdict(verdict="no_trade"), _SHRINK)
    assert out.confluence_score == 0.0
    assert out.overall_bias == "Neutral"


def test_agreement_applies_shrinkage():
    out = apply_trader_verdict(
        _synthesis(bias="Bullish"), _verdict(verdict="long", conviction=0.8), _SHRINK
    )
    assert out.overall_bias == "Bullish"
    assert out.confluence_score == pytest.approx(0.8 * _SHRINK)


def test_disagreement_adds_penalty():
    # synthesis bullish, trader short → disagreement → extra 0.5 haircut
    out = apply_trader_verdict(
        _synthesis(bias="Bullish"), _verdict(verdict="short", conviction=0.8), _SHRINK
    )
    assert out.overall_bias == "Bearish"
    assert out.confluence_score == pytest.approx(0.8 * _SHRINK * 0.5)


class _FakeService:
    """Возвращает ResearchCase для bull/bear, TraderVerdict для trader."""

    def __init__(self, bull_conv: float, bear_conv: float, verdict: TraderVerdict):
        self._bull = ResearchCase(thesis="bull", key_points=["a"], conviction=bull_conv)
        self._bear = ResearchCase(thesis="bear", key_points=["b"], conviction=bear_conv)
        self._verdict = verdict
        self.entity_types: list[str] = []

    async def structured(self, **kwargs: object):
        entity = kwargs["entity_type"]
        self.entity_types.append(entity)  # type: ignore[arg-type]
        if entity == "bull":
            return self._bull
        if entity == "bear":
            return self._bear
        return self._verdict


def _reports():
    macro = MacroReport(
        reasoning="r",
        regime="Trending Up",
        btc_bias="Bullish",
        dominance_trend="Flat",
        alts_tradeable=True,
    )
    deriv = DerivativesReport(
        key_insight="k",
        funding_signal="Neutral",
        oi_signal="Neutral",
        ls_signal="Balanced",
        liq_nearest_long=None,
        liq_nearest_short=None,
        cvd_direction="Neutral",
        overall_bias="Bullish",
    )
    senti = SentimentReport(
        key_insight="k",
        social_sentiment="Bullish",
        fear_greed_label="Neutral",
        news_sentiment="Neutral",
        overall_bias="Bullish",
    )
    tech = TechnicalReport(
        market_structure="m",
        htf_bias="Bullish",
        setup_bias="Bullish",
        key_levels=[],
        entry_timeframe_note="n",
        signal_direction="Long",
        confidence=0.6,
    )
    return macro, deriv, senti, tech


async def test_run_debate_calls_bull_bear_trader():
    service = _FakeService(0.7, 0.3, _verdict(verdict="long", conviction=0.7))
    macro, deriv, senti, tech = _reports()
    bull, bear, verdict = await run_debate(
        service,  # type: ignore[arg-type]
        "BTC/USDT:USDT",
        macro,
        deriv,
        senti,
        tech,
        _synthesis(),
    )
    assert bull.conviction == 0.7
    assert bear.conviction == 0.3
    assert verdict.verdict == "long"
    assert set(service.entity_types) == {"bull", "bear", "trader"}
