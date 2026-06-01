import logging

from app.exceptions import StartupError
from core.constants.llm import LLMProvider
from core.settings import settings

logger = logging.getLogger(__name__)


def required_keys() -> dict[str, str]:
    """Обязательные env-ключи под выбранного LLM-провайдера (имя → значение)."""
    keys = {
        "LUNARCRUSH_API_KEY": settings.LUNARCRUSH_API_KEY,
        "COINGLASS_API_KEY": settings.COINGLASS_API_KEY,
    }
    if settings.LLM_PROVIDER == LLMProvider.OPENAI:
        keys["OPENAI_API_KEY"] = settings.OPENAI_API_KEY
    else:
        keys["ANTHROPIC_API_KEY"] = settings.ANTHROPIC_API_KEY
    return keys


def preflight() -> None:
    """Проверяет наличие обязательных ключей под выбранного провайдера. Иначе StartupError."""
    missing = [name for name, value in required_keys().items() if not value]
    if missing:
        raise StartupError(f"missing required env keys: {', '.join(sorted(missing))}")
    logger.info(
        "preflight ok (provider=%s, telegram=%s)",
        settings.LLM_PROVIDER.value,
        "on" if settings.TELEGRAM_ENABLED else "off",
    )
