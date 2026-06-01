import logging
from collections.abc import Callable

from app.clients.ccxt.models import OHLCVCandle
from app.models.setup import CryptoSetup, SetupIntent
from app.screener.indicators import calc_atr
from core.constants.time import FUNDING_CYCLE_HOURS

logger = logging.getLogger(__name__)

_DEFAULT_SWING_LOOKBACK = 20
_MIN_STOP_DISTANCE_PCT = 0.003
_MAX_STOP_DISTANCE_PCT = 0.08
_MAX_TARGET_DISTANCE_PCT = 0.20
_KIND_ATR = "atr_distance"
_DEFAULT_ATR_MULTIPLIER = 2.0
_DEFAULT_TARGET_ATR_MULTIPLIER = 3.0
_FALLBACK_TARGET_RR = 2.0


def _swing_high(candles_4h: list[OHLCVCandle], lookback: int) -> float:
    return max(candle.high for candle in candles_4h[-lookback:])


def _swing_low(candles_4h: list[OHLCVCandle], lookback: int) -> float:
    return min(candle.low for candle in candles_4h[-lookback:])


def _prev_day_high(candles_1d: list[OHLCVCandle]) -> float | None:
    return candles_1d[-2].high if len(candles_1d) >= 2 else None


def _prev_day_low(candles_1d: list[OHLCVCandle]) -> float | None:
    return candles_1d[-2].low if len(candles_1d) >= 2 else None


_AnchorResolver = Callable[[list[OHLCVCandle], list[OHLCVCandle], int], float | None]

_ANCHOR_RESOLVERS: dict[str, _AnchorResolver] = {
    "swing_high_4h": lambda c4, _c1, lb: _swing_high(c4, lb),
    "swing_low_4h": lambda c4, _c1, lb: _swing_low(c4, lb),
    "prev_day_high": lambda _c4, c1, _lb: _prev_day_high(c1),
    "prev_day_low": lambda _c4, c1, _lb: _prev_day_low(c1),
}


def _resolve_anchor(
    kind: str,
    lookback: int | None,
    candles_4h: list[OHLCVCandle],
    candles_1d: list[OHLCVCandle],
) -> float | None:
    resolver = _ANCHOR_RESOLVERS.get(kind)
    if resolver is None:
        return None
    return resolver(candles_4h, candles_1d, lookback or _DEFAULT_SWING_LOOKBACK)


def _ordering_ok(is_long: bool, entry: float, stop: float, target: float) -> bool:
    if is_long:
        return stop < entry < target
    return target < entry < stop


def resolve_setup(
    intent: SetupIntent,
    candles_4h: list[OHLCVCandle],
    candles_1d: list[OHLCVCandle],
    current_price: float,
    funding_rate: float,
) -> CryptoSetup | None:
    """Резолвит SetupIntent в реальные цены (CryptoSetup) детерминированно.

    Вход исполняется по market (current_price) — лимитный entry-якорь LLM остаётся в
    SetupIntent как замысел, но фактический филл всегда по текущей цене (без фантомных
    лимитных заполнений). Стоп/цель считаются относительно market-входа. None — если
    стоп вне [0.3%, 8%] или сетап не проходит sanity по порядку уровней; выше это
    становится no_trade.
    """
    if not candles_4h or current_price <= 0:
        return None
    atr = calc_atr(candles_4h)
    if atr <= 0:
        return None
    is_long = intent.direction == "long"
    entry = current_price

    if intent.stop.kind == _KIND_ATR:
        raw_distance = (intent.stop.atr_multiplier or _DEFAULT_ATR_MULTIPLIER) * atr
        distance = min(
            max(raw_distance, _MIN_STOP_DISTANCE_PCT * entry),
            _MAX_STOP_DISTANCE_PCT * entry,
        )
        stop = entry - distance if is_long else entry + distance
    else:
        stop_anchor = _resolve_anchor(
            intent.stop.kind, intent.stop.lookback, candles_4h, candles_1d
        )
        if stop_anchor is None:
            return None
        offset = intent.stop_offset_atr * atr
        stop = stop_anchor - offset if is_long else stop_anchor + offset
        anchor_distance_pct = abs(entry - stop) / entry
        if not _MIN_STOP_DISTANCE_PCT <= anchor_distance_pct <= _MAX_STOP_DISTANCE_PCT:
            logger.info(
                "setup rejected: stop distance %.3f%% out of bounds",
                anchor_distance_pct * 100,
            )
            return None

    if (
        min(entry, stop) <= 0
        or (is_long and stop >= entry)
        or (not is_long and stop <= entry)
    ):
        logger.info("setup rejected: bad entry/stop ordering (%s)", intent.direction)
        return None

    if intent.target.kind == _KIND_ATR:
        distance = (
            intent.target.atr_multiplier or _DEFAULT_TARGET_ATR_MULTIPLIER
        ) * atr
        target: float | None = entry + distance if is_long else entry - distance
    else:
        target = _resolve_anchor(
            intent.target.kind, intent.target.lookback, candles_4h, candles_1d
        )
    if target is None or target <= 0 or not _ordering_ok(is_long, entry, stop, target):
        risk = abs(entry - stop)
        target = (
            entry + _FALLBACK_TARGET_RR * risk
            if is_long
            else entry - _FALLBACK_TARGET_RR * risk
        )
        logger.info(
            "target fallback to %.1fR measured move (%s)",
            _FALLBACK_TARGET_RR,
            intent.direction,
        )

    max_target_distance = _MAX_TARGET_DISTANCE_PCT * entry
    if abs(target - entry) > max_target_distance:
        target = entry + max_target_distance if is_long else entry - max_target_distance
        logger.info(
            "target capped to %.0f%% distance (%s)",
            _MAX_TARGET_DISTANCE_PCT * 100,
            intent.direction,
        )

    return CryptoSetup(
        direction=intent.direction,
        setup_type=intent.setup_type,
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        risk_reward=abs(target - entry) / abs(entry - stop),
        valid_hours=intent.valid_hours,
        funding_impact_pct=funding_rate * intent.valid_hours / FUNDING_CYCLE_HOURS,
        invalidation=(f"4h close {'below' if is_long else 'above'} {stop:.6g}"),
        leverage_intent=intent.leverage_intent,
    )
