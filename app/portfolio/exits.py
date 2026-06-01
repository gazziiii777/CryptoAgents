import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.clients.ccxt.models import OHLCVCandle
from app.portfolio.models import ExitOutcome
from core.constants.time import (
    FUNDING_CYCLE_HOURS,
    MINUTES_PER_HOUR,
    MS_PER_SECOND,
    SECONDS_PER_MINUTE,
)
from db.models import ExitReason, PositionSide

_CYCLE_SECONDS = FUNDING_CYCLE_HOURS * MINUTES_PER_HOUR * SECONDS_PER_MINUTE


def _stop_reason(
    effective_stop: Decimal, entry: Decimal, initial_stop: Decimal
) -> ExitReason:
    if effective_stop == initial_stop:
        return ExitReason.STOP
    if effective_stop == entry:
        return ExitReason.BREAKEVEN
    return ExitReason.TRAILING_STOP


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


def walk_managed_exit(
    side: PositionSide,
    entry: Decimal,
    initial_stop: Decimal,
    target: Decimal,
    candles: list[OHLCVCandle],
    entry_ts: datetime,
    breakeven_trigger_r: float,
    trail_activation_r: float,
    trail_distance_r: float,
) -> tuple[ExitOutcome | None, float]:
    """Управляемый выход по свечам: стоп в безубыток на +1R, затем трейлинг.

    Stateless-реконструкция: на каждой свече проверяем пробой ТЕКУЩЕГО стопа (рассчитан
    по предыдущим свечам — без look-ahead) и цели (стоп приоритетнее внутри свечи), затем
    обновляем favorable_extreme и подтягиваем стоп (только в выгодную сторону). Возвращает
    (исход или None, max favorable excursion в R). Если R вырождена — обычный stop/target.
    """
    is_long = side == PositionSide.LONG
    r = abs(entry - initial_stop)
    effective_stop = initial_stop
    favorable_extreme = entry
    mfe_r = 0.0
    trail_distance = r * Decimal(str(trail_distance_r))

    for candle in candles:
        candle_ts = datetime.fromtimestamp(
            candle.timestamp / MS_PER_SECOND, tz=timezone.utc
        )
        if candle_ts <= entry_ts:
            continue
        high = Decimal(str(candle.high))
        low = Decimal(str(candle.low))

        if is_long:
            if low <= effective_stop:
                reason = _stop_reason(effective_stop, entry, initial_stop)
                return ExitOutcome(reason, effective_stop, candle_ts), mfe_r
            if high >= target:
                return ExitOutcome(ExitReason.TARGET, target, candle_ts), mfe_r
            favorable_extreme = max(favorable_extreme, high)
        else:
            if high >= effective_stop:
                reason = _stop_reason(effective_stop, entry, initial_stop)
                return ExitOutcome(reason, effective_stop, candle_ts), mfe_r
            if low <= target:
                return ExitOutcome(ExitReason.TARGET, target, candle_ts), mfe_r
            favorable_extreme = min(favorable_extreme, low)

        if r <= 0:
            continue
        favorable = favorable_extreme - entry if is_long else entry - favorable_extreme
        mfe_r = max(mfe_r, float(favorable / r))
        new_stop = effective_stop
        if mfe_r >= trail_activation_r:
            new_stop = (
                favorable_extreme - trail_distance
                if is_long
                else favorable_extreme + trail_distance
            )
        elif mfe_r >= breakeven_trigger_r:
            new_stop = entry
        effective_stop = (
            max(effective_stop, new_stop) if is_long else min(effective_stop, new_stop)
        )

    return None, mfe_r


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
