from app.domain.models.screener import Direction, SignalDetails, SmartMoneyDivergence
from core.settings import settings


def compute_direction(sig: SignalDetails) -> Direction:
    """Голосование по направленным сигналам: 'long', 'short' или 'mixed'.

    Порог ±DIRECTION_VOTE_THRESHOLD: минимум столько перевесов в одну сторону.
    Контрарные сигналы (retail L/S, funding, OI-weighted funding, basis) инвертированы.
    """
    votes = 0

    if sig.ema_cross == "golden":
        votes += 1
    elif sig.ema_cross == "death":
        votes -= 1

    if sig.rsi_divergence == "bullish":
        votes += 1
    elif sig.rsi_divergence == "bearish":
        votes -= 1

    if sig.macd == "bullish":
        votes += 1
    elif sig.macd == "bearish":
        votes -= 1

    if sig.cvd_price_divergence == "bullish":
        votes += 1
    elif sig.cvd_price_divergence == "bearish":
        votes -= 1

    if sig.daily_trend == "up":
        votes += 1
    elif sig.daily_trend == "down":
        votes -= 1

    if sig.vwap_bias == "above":
        votes += 1
    elif sig.vwap_bias == "below":
        votes -= 1

    if sig.cvd_trend == "rising":
        votes += 1
    elif sig.cvd_trend == "falling":
        votes -= 1

    ls = sig.long_short_ratio
    if ls is not None:
        if ls >= settings.LS_RATIO_HIGH:
            votes -= 1
        elif ls <= settings.LS_RATIO_LOW:
            votes += 1

    top_ls = sig.top_trader_ls_ratio
    if top_ls is not None:
        if top_ls >= settings.LS_RATIO_HIGH:
            votes += 1
        elif top_ls <= settings.LS_RATIO_LOW:
            votes -= 1

    funding = (
        sig.oi_weighted_funding_bias
        if sig.oi_weighted_funding_bias != "neutral"
        else sig.funding_bias
    )
    if funding == "long_heavy":
        votes -= 1
    elif funding == "short_heavy":
        votes += 1

    basis = sig.basis
    if basis is not None:
        if basis >= settings.BASIS_CONTANGO_THRESHOLD:
            votes += 1
        elif basis <= -settings.BASIS_CONTANGO_THRESHOLD:
            votes -= 1

    if votes >= settings.DIRECTION_VOTE_THRESHOLD:
        return "long"
    if votes <= -settings.DIRECTION_VOTE_THRESHOLD:
        return "short"
    return "mixed"


def classify_smart_money_divergence(
    retail_ls: float | None, top_ls: float | None, high: float, low: float
) -> SmartMoneyDivergence:
    """Расхождение smart money (top traders) с ретейл-толпой.

    'diverges_bearish' — ретейл в эйфории лонгует (retail >= high), а топ-трейдеры НЕ
    в лонге: умные деньги распределяют в толпу → медвежий контрарный сигнал.
    'diverges_bullish' — ретейл капитулировал в шорт (retail <= low), топ в лонге:
    умные деньги накапливают → бычий. 'confirms' — обе стороны согласны. Иначе/нет
    данных — 'neutral'. Учитывает только направление, не размер (account-ratio врёт о
    капитале — это sentiment-фича, не евангелие).
    """
    if retail_ls is None or top_ls is None:
        return "neutral"
    retail_long = retail_ls >= high
    retail_short = retail_ls <= low
    top_long = top_ls > 1.0
    top_short = top_ls < 1.0
    if retail_long and top_short:
        return "diverges_bearish"
    if retail_short and top_long:
        return "diverges_bullish"
    if (retail_long and top_long) or (retail_short and top_short):
        return "confirms"
    return "neutral"


def compute_score(sig: SignalDetails) -> int:
    """Сумма сработавших критериев (max 15): активность + momentum + derivatives."""
    score = 0

    if sig.volume_spike:
        score += 1
    if sig.bb_squeeze:
        score += 1
    if sig.near_swing:
        score += 1

    if sig.ema_cross is not None:
        score += 1
    if sig.rsi_divergence is not None:
        score += 1
    if sig.macd is not None:
        score += 1
    if sig.cvd_price_divergence is not None:
        score += 1

    rsi = sig.rsi_level
    if rsi is not None and (
        rsi >= settings.RSI_OVERBOUGHT or rsi <= settings.RSI_OVERSOLD
    ):
        score += 1

    ls = sig.long_short_ratio
    if ls is not None and (ls >= settings.LS_RATIO_HIGH or ls <= settings.LS_RATIO_LOW):
        score += 1

    top_ls = sig.top_trader_ls_ratio
    if top_ls is not None and (
        top_ls >= settings.LS_RATIO_HIGH or top_ls <= settings.LS_RATIO_LOW
    ):
        score += 1

    if (sig.daily_trend == "up" and sig.vwap_bias == "above") or (
        sig.daily_trend == "down" and sig.vwap_bias == "below"
    ):
        score += 1

    if sig.funding_bias != "neutral" or sig.oi_weighted_funding_bias != "neutral":
        score += 1
    if sig.oi_trend != "neutral":
        score += 1

    if abs(sig.oi_change_4h_pct) >= settings.OI_CHANGE_4H_SCORE_PCT:
        score += 1

    if sig.liq_spike:
        score += 1

    return score
