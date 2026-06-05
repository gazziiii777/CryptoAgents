from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from db.models import ExitReason


@dataclass(frozen=True, slots=True)
class ExitOutcome:
    """Решение о закрытии позиции: причина, цена и момент выхода."""

    reason: ExitReason
    price: Decimal
    ts: datetime
