import logging
from datetime import datetime

from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.clients.llm.models import LLMUsage
from app.llm_gateway.errors import LLMBudgetExceededError
from core.settings import settings
from db._time import utcnow
from db.models import EventType
from db.repositories.event_repo import EventRepo

logger = logging.getLogger(__name__)


def _utc_day_start(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


class DailyBudgetGuard:
    """Hard cap на суммарную стоимость LLM-вызовов в текущих UTC-сутках.

    Сумма берётся из Event(llm_call).payload_json['cost_usd']. Cap — soft при гонке
    параллельных вызовов (проверка и списание не атомарны), допустим небольшой перебор;
    для MVP приемлемо.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._events = EventRepo(session)

    async def spent_today(self) -> float:
        since = _utc_day_start(utcnow())
        events = await self._events.list_by_type_since(EventType.LLM_CALL, since)
        total = 0.0
        for event in events:
            if not event.payload_json:
                continue
            try:
                total += LLMUsage.model_validate(event.payload_json).cost_usd
            except ValidationError:
                logger.warning(
                    "Skipping malformed llm_call event in budget calc event_id=%s",
                    event.id,
                )
        return total

    async def ensure_within_budget(self) -> None:
        spent = await self.spent_today()
        if spent >= settings.LLM_DAILY_BUDGET_USD:
            logger.warning(
                "LLM daily budget exceeded spent_usd=%.4f cap_usd=%.2f",
                spent,
                settings.LLM_DAILY_BUDGET_USD,
            )
            raise LLMBudgetExceededError(
                f"LLM daily budget ${settings.LLM_DAILY_BUDGET_USD:.2f} reached "
                f"(spent ${spent:.4f})"
            )
