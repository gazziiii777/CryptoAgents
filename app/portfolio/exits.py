import math
from datetime import datetime, timedelta
from decimal import Decimal

from app.clients.ccxt.models import OHLCVCandle
from app.portfolio.models import ExitOutcome
from core.constants.time import (
    FUNDING_CYCLE_HOURS,
    MINUTES_PER_HOUR,
    SECONDS_PER_MINUTE,
)
from db.models import ExitReason, PositionSide

_CYCLE_SECONDS = FUNDING_CYCLE_HOURS * MINUTES_PER_HOUR * SECONDS_PER_MINUTE


def evaluate_candle_exit(
    side: PositionSide,
    stop_price: Decimal,
    target_price: Decimal,
    candle: OHLCVCandle,
    candle_close_ts: datetime,
) -> ExitOutcome | None:
    """Проверка stop/target по одной 4h-свече.

    Если в свече задеты оба уровня — стоп приоритетнее (консервативная оценка для paper).
    """
    high = Decimal(str(candle.high))
    low = Decimal(str(candle.low))
    if side == PositionSide.LONG:
        if low <= stop_price:
            return ExitOutcome(ExitReason.STOP, stop_price, candle_close_ts)
        if high >= target_price:
            return ExitOutcome(ExitReason.TARGET, target_price, candle_close_ts)
    else:
        if high >= stop_price:
            return ExitOutcome(ExitReason.STOP, stop_price, candle_close_ts)
        if low <= target_price:
            return ExitOutcome(ExitReason.TARGET, target_price, candle_close_ts)
    return None


def is_expired(entry_ts: datetime, valid_hours: int, now: datetime) -> bool:
    """Истёк ли срок жизни сетапа (entry_ts + valid_hours)."""
    return now >= entry_ts + timedelta(hours=valid_hours)


def funding_cycles(entry_ts: datetime, exit_ts: datetime) -> int:
    """Число пройденных 8h funding-границ (00/08/16 UTC) за время удержания."""
    if exit_ts <= entry_ts:
        return 0
    start = math.floor(entry_ts.timestamp() / _CYCLE_SECONDS)
    end = math.floor(exit_ts.timestamp() / _CYCLE_SECONDS)
    return max(0, end - start)
