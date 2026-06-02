from collections import defaultdict

from app.clients.ccxt.models import OHLCVCandle
from app.models.liquidity import LiquidityLevel
from core.constants.liquidity import LEVERAGE_TIERS
from core.settings import settings


def estimate_liquidation_clusters(
    candles: list[OHLCVCandle], mark_price: float
) -> list[LiquidityLevel]:
    """Прокси-кластеры ликвидаций из volume profile.

    Узлы объёма = зоны входа толпы. Для каждого узла и каждого плечевого тира
    считаем цену ликвидации лонгов/шортов, копим веса в ценовой сетке. Самые
    плотные бины — магниты, к которым тянет цену снимать стопы. Кластеры выше
    mark_price помечаются как short_liq (топливо вверх), ниже — long_liq (вниз).
    """
    nodes = _volume_profile(candles)
    if not nodes or mark_price <= 0:
        return []
    step = mark_price * settings.LIQUIDITY_CLUSTER_BIN_PCT
    densities = _accumulate(nodes, step)
    return _top_clusters(densities, step, mark_price)


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


def _accumulate(nodes: list[tuple[float, float]], step: float) -> dict[int, float]:
    densities: dict[int, float] = defaultdict(float)
    tier_weight = 1.0 / len(LEVERAGE_TIERS)
    for node_price, volume in nodes:
        for tier in LEVERAGE_TIERS:
            inverse_leverage = 1.0 / tier
            long_liq = node_price * (1.0 - inverse_leverage)
            short_liq = node_price * (1.0 + inverse_leverage)
            densities[round(long_liq / step)] += volume * tier_weight
            densities[round(short_liq / step)] += volume * tier_weight
    return densities


def _top_clusters(
    densities: dict[int, float], step: float, mark_price: float
) -> list[LiquidityLevel]:
    if not densities:
        return []
    max_weight = max(densities.values())
    if max_weight <= 0:
        return []
    ranked = sorted(densities.items(), key=lambda item: item[1], reverse=True)
    clusters: list[LiquidityLevel] = []
    for index, weight in ranked[: settings.LIQUIDITY_TOP_CLUSTERS]:
        price = index * step
        if price <= 0 or price == mark_price:
            continue
        kind = "short_liq_cluster" if price > mark_price else "long_liq_cluster"
        clusters.append(
            LiquidityLevel(price=price, kind=kind, strength=weight / max_weight)
        )
    return clusters
