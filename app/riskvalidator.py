import logging

from app.models.setup import CryptoSetup
from core.settings import settings

logger = logging.getLogger(__name__)


def validate_risk(setup: CryptoSetup) -> str | None:
    """Проверка риск-правил CryptoSetup. None = прошёл, str = причина отказа.

    Дистанция стопа гарантирована LevelComputer'ом (∈[0.3%,5%]), тут — R:R и funding.
    """
    if setup.risk_reward < settings.RISK_REWARD_MIN:
        return f"R:R {setup.risk_reward:.2f} < {settings.RISK_REWARD_MIN}"
    if abs(setup.funding_impact_pct) > settings.FUNDING_COST_MAX_PCT:
        return (
            f"funding cost {abs(setup.funding_impact_pct) * 100:.2f}% over hold exceeds "
            f"{settings.FUNDING_COST_MAX_PCT * 100:.2f}%"
        )
    return None
