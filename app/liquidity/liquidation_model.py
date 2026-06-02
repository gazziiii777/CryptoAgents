from collections import defaultdict

from app.clients.ccxt.models import OHLCVCandle
from app.models.liquidity import LiquidityKind, LiquidityLevel
from core.constants.liquidity import LEVERAGE_TIERS
from core.settings import settings


def estimate_liquidation_clusters(
    candles: list[OHLCVCandle], mark_price: float
) -> list[LiquidityLevel]:
    """Прокси-кластеры ликвидаций из volume profile.

    Узлы объёма = зоны входа толпы. Для каждого узла и плечевого тира считаем цену
    ликвидации лонгов (ниже узла) и шортов (выше узла) в РАЗДЕЛЬНЫЕ ценовые сетки,
    чтобы kind отражал природу ликвидации (что сливается), а не положение бина
    относительно mark. Самые плотные бины — магниты, к которым тянет цену снимать
    стопы. Сила нормирована по общему максимуму, чтобы long/short сравнивались.
    """
    nodes = _volume_profile(candles)
    if not nodes or mark_price <= 0:
        return []
    step = mark_price * settings.LIQUIDITY_CLUSTER_BIN_PCT
    long_liq, short_liq = _accumulate(nodes, step)
    max_weight = max([*long_liq.values(), *short_liq.values()], default=0.0)
    if max_weight <= 0:
        return []
    return _top_clusters(
        long_liq, "long_liq_cluster", step, max_weight
    ) + _top_clusters(short_liq, "short_liq_cluster", step, max_weight)


def _volume_profile(candles: list[OHLCVCandle]) -> list[tuple[float, float]]:
    window = candles[-settings.LIQUIDITY_PROFILE_WINDOW :]
    if not window:
        return []
    low = min(candle.low for candle in window)
    high = max(candle.high for candle in window)
    if high <= low:
        return []
    bins = settings.LIQUIDITY_PROFILE_BINS
    width = (high - low) / bins
    buckets: dict[int, float] = defaultdict(float)
    for candle in window:
        typical_price = (candle.high + candle.low + candle.close) / 3
        index = min(int((typical_price - low) / width), bins - 1)
        buckets[index] += candle.volume
    return [(low + (index + 0.5) * width, volume) for index, volume in buckets.items()]


def _accumulate(
    nodes: list[tuple[float, float]], step: float
) -> tuple[dict[int, float], dict[int, float]]:
    long_liq: dict[int, float] = defaultdict(float)
    short_liq: dict[int, float] = defaultdict(float)
    tier_weight = 1.0 / len(LEVERAGE_TIERS)
    for node_price, volume in nodes:
        for tier in LEVERAGE_TIERS:
            inverse_leverage = 1.0 / tier
            long_liq[round(node_price * (1.0 - inverse_leverage) / step)] += (
                volume * tier_weight
            )
            short_liq[round(node_price * (1.0 + inverse_leverage) / step)] += (
                volume * tier_weight
            )
    return long_liq, short_liq


def _top_clusters(
    densities: dict[int, float], kind: LiquidityKind, step: float, max_weight: float
) -> list[LiquidityLevel]:
    ranked = sorted(densities.items(), key=lambda item: item[1], reverse=True)
    clusters: list[LiquidityLevel] = []
    for index, weight in ranked[: settings.LIQUIDITY_TOP_CLUSTERS]:
        price = index * step
        if price <= 0:
            continue
        clusters.append(
            LiquidityLevel(price=price, kind=kind, strength=weight / max_weight)
        )
    return clusters
