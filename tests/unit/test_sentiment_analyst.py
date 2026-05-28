from app.models.analysis import SentimentReport
from core.prompts.loader import load_prompt
from app.analysts.sentiment import _render_user_prompt, analyze_sentiment
from app.clients.lunarcrush.models import LunarCrushCoinMetrics
from app.enricher.insight import derive_social_insight


def _social():
    lc = LunarCrushCoinMetrics(symbol="ZEC", sentiment=83.0, galaxy_score=63.8)
    return derive_social_insight(
        lc=lc,
        news=[],
        posts=[],
        whatsup=None,
        time_series=[],
        screener_direction="long",
    )


def test_render_includes_sentiment_and_fear_greed():
    template = load_prompt("sentiment").user
    prompt = _render_user_prompt(template, _social(), fear_greed=64)
    assert "83%" in prompt
    assert "63.8" in prompt
    assert "Fear & Greed index (0-100): 64" in prompt


def test_render_handles_missing_fear_greed():
    template = load_prompt("sentiment").user
    assert "n/a" in _render_user_prompt(template, _social(), fear_greed=None)


class _FakeService:
    def __init__(self, report: SentimentReport) -> None:
        self._report = report
        self.calls: list[dict[str, object]] = []

    async def structured(self, **kwargs: object) -> SentimentReport:
        self.calls.append(kwargs)
        return self._report


async def test_analyze_sentiment_passes_response_model():
    expected = SentimentReport(
        key_insight="bullish social",
        social_sentiment="Bullish",
        fear_greed_label="Neutral",
        news_sentiment="Neutral",
        overall_bias="Bullish",
    )
    service = _FakeService(expected)

    result = await analyze_sentiment(service, _social(), fear_greed=64)  # type: ignore[arg-type]

    assert result is expected
    assert service.calls[0]["response_model"] is SentimentReport
    assert service.calls[0]["entity_type"] == "sentiment"
