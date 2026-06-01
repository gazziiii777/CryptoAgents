import logging

from app.models.setup import CryptoSetup
from core.settings import settings

logger = logging.getLogger(__name__)


def validate_risk(setup: CryptoSetup) -> str | None:
    """Проверка риск-правил CryptoSetup. None = прошёл, str = причина отказа.

    Дистанция стопа гарантирована LevelComputer'ом (∈[0.3%,8%]), тут — R:R и funding.
    Фандинг берётся со знаком стороны: при положительном funding_rate лонг платит,
    шорт получает (funding_impact_pct посчитан как стоимость для лонга). Гейт режет
    только когда фандинг для нашей стороны — реальный расход, а не доход.
    """
    if setup.risk_reward < settings.RISK_REWARD_MIN:
        return f"R:R {setup.risk_reward:.2f} < {settings.RISK_REWARD_MIN}"
    funding_cost_pct = (
        setup.funding_impact_pct
        if setup.direction == "long"
        else -setup.funding_impact_pct
    )
    if funding_cost_pct > settings.FUNDING_COST_MAX_PCT:
        return (
            f"funding cost {funding_cost_pct * 100:.2f}% over hold exceeds "
            f"{settings.FUNDING_COST_MAX_PCT * 100:.2f}%"
        )
    return None
