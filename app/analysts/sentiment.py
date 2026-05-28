import logging
from string import Template

from app.models.analysis import SentimentReport
from core.prompts.loader import load_prompt
from app.llm_gateway.service import LLMService
from app.models.enricher import SocialInsight
from core.settings import settings

logger = logging.getLogger(__name__)

_ENTITY_TYPE = "sentiment"


def _render_user_prompt(
    template: str, social: SocialInsight, fear_greed: int | None
) -> str:
    return Template(template).substitute(
        sentiment_pct=f"{social.sentiment_pct:.0f}"
        if social.sentiment_pct is not None
        else "n/a",
        sentiment_direction=social.sentiment_direction,
        attention_level=social.attention_level,
        momentum=social.momentum,
        galaxy_score=f"{social.galaxy_score:.1f}"
        if social.galaxy_score is not None
        else "n/a",
        contrarian_warning=str(social.contrarian_warning),
        news_count=str(social.important_news_count_24h),
        catalyst_polarity=social.catalyst_polarity or "n/a",
        influencer_mentions=str(social.influencer_mentions),
        pump_risk=social.pump_risk,
        fear_greed=str(fear_greed) if fear_greed is not None else "n/a",
    )


async def analyze_sentiment(
    service: LLMService, social: SocialInsight, fear_greed: int | None = None
) -> SentimentReport:
    """Sentiment-аналитик: SocialInsight + fear&greed → SentimentReport."""
    prompt = load_prompt(_ENTITY_TYPE)
    report = await service.structured(
        model=settings.LLM_QUICK_MODEL,
        system=prompt.system,
        user=_render_user_prompt(prompt.user, social, fear_greed),
        response_model=SentimentReport,
        entity_type=_ENTITY_TYPE,
    )
    logger.info(
        "sentiment analysis complete",
        extra={"analyst": _ENTITY_TYPE, "result": report.model_dump(mode="json")},
    )
    return report
