from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

_FROZEN = ConfigDict(frozen=True, extra="ignore")


def _to_float_or_none(v: object) -> float | None:
    if not isinstance(v, str | int | float):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int_or_none(v: object) -> int | None:
    if not isinstance(v, str | int | float):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _to_int_zero(v: object) -> int:
    parsed = _to_int_or_none(v)
    return parsed if parsed is not None else 0


def _to_float_zero(v: object) -> float:
    parsed = _to_float_or_none(v)
    return parsed if parsed is not None else 0.0


def _to_str_or_none(v: object) -> str | None:
    if v is None:
        return None
    s = str(v)
    return s or None


def _to_str_empty(v: object) -> str:
    return str(v) if v else ""


def _unix_to_datetime(v: object) -> datetime | None:
    """Unix timestamp (секунды) → tz-aware UTC datetime; datetime пропускается as-is."""
    if v is None or isinstance(v, datetime):
        return v
    if not isinstance(v, str | int | float):
        return None
    try:
        return datetime.fromtimestamp(int(v), tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


def _unix_to_datetime_now(v: object) -> datetime:
    return _unix_to_datetime(v) or datetime.now(UTC)


def _split_categories(v: object) -> list[str]:
    if isinstance(v, list):
        return [str(c) for c in v]
    if not v or not isinstance(v, str):
        return []
    return [c.strip() for c in v.split(",") if c.strip()]


def _to_themes_list(v: object) -> list[object]:
    return v if isinstance(v, list) else []


FloatOrNone = Annotated[float | None, BeforeValidator(_to_float_or_none)]
IntOrNone = Annotated[int | None, BeforeValidator(_to_int_or_none)]
IntZero = Annotated[int, BeforeValidator(_to_int_zero)]
FloatZero = Annotated[float, BeforeValidator(_to_float_zero)]
StrOrNone = Annotated[str | None, BeforeValidator(_to_str_or_none)]
StrEmpty = Annotated[str, BeforeValidator(_to_str_empty)]
DatetimeOrNone = Annotated[datetime | None, BeforeValidator(_unix_to_datetime)]
DatetimeOrNow = Annotated[datetime, BeforeValidator(_unix_to_datetime_now)]
Categories = Annotated[list[str], BeforeValidator(_split_categories)]


class LunarCrushCoinMetrics(BaseModel):
    """Метрики из LunarCrush /coins/list/v1 для одной монеты.

    topic — slug для /topic/{topic}/* запросов: имя без символа-префикса из поля
    "topic" (напр. "btc bitcoin" → "bitcoin", "near near protocol" → "near protocol").
    sentiment — 0..100 (% позитивных постов взвешенных по interactions).
    """

    model_config = _FROZEN

    symbol: str
    name: StrOrNone = None
    topic: StrOrNone = None
    galaxy_score: FloatOrNone = None
    galaxy_score_previous: FloatOrNone = None
    alt_rank: IntOrNone = None
    alt_rank_previous: IntOrNone = None
    sentiment: FloatOrNone = None
    social_volume_24h: IntOrNone = None
    interactions_24h: IntOrNone = None
    social_dominance: FloatOrNone = None
    categories: Categories = Field(default_factory=list)


class WhatsupTheme(BaseModel):
    """Тема из AI-summary LunarCrush /topic/{topic}/whatsup/v1."""

    model_config = _FROZEN

    title: StrEmpty = ""
    description: StrEmpty = ""
    percent: FloatZero = 0.0


class WhatsupSummary(BaseModel):
    """AI-сгенерированный narrative от LunarCrush.

    Покрывает что обсуждается, какие supportive/critical темы. Заменяет
    отдельный LLM-вызов для narrative-анализа.
    """

    model_config = _FROZEN

    summary: str
    supportive: Annotated[list[WhatsupTheme], BeforeValidator(_to_themes_list)] = Field(
        default_factory=list
    )
    critical: Annotated[list[WhatsupTheme], BeforeValidator(_to_themes_list)] = Field(
        default_factory=list
    )


class LunarCrushPost(BaseModel):
    """Социальный пост от LunarCrush /topic/{topic}/posts/v1.

    creator_followers — ключевое поле для отделения retail от influencers.
    post_sentiment — 1-5 (1=very negative, 3=neutral, 5=very positive).
    """

    model_config = _FROZEN

    id: StrEmpty = ""
    post_type: StrEmpty = ""
    post_title: StrOrNone = None
    post_link: StrOrNone = None
    post_created: DatetimeOrNone = None
    post_sentiment: FloatOrNone = None
    creator_name: StrOrNone = None
    creator_display_name: StrOrNone = None
    creator_followers: IntZero = 0
    interactions_24h: IntZero = 0


class LunarCrushNewsItem(BaseModel):
    """Новость от LunarCrush /topic/{topic}/news/v1.

    Уже отсортированы по социальной обсуждаемости (top news = top in social),
    что лучше CryptoPanic-сортировки по community votes.
    """

    model_config = _FROZEN

    id: StrEmpty = ""
    post_title: StrEmpty = ""
    post_description: StrOrNone = None
    post_link: StrOrNone = None
    post_created: DatetimeOrNone = None
    post_sentiment: FloatOrNone = None
    creator_name: StrOrNone = None
    creator_followers: IntZero = 0
    interactions_24h: IntZero = 0


class CoinTimeSeriesPoint(BaseModel):
    """Точка time-series для расчёта baseline по социальной активности."""

    model_config = _FROZEN

    time: DatetimeOrNow
    close: FloatOrNone = None
    sentiment: FloatOrNone = None
    interactions: IntOrNone = None
    posts_active: IntOrNone = None
    galaxy_score: FloatOrNone = None
    alt_rank: IntOrNone = None
