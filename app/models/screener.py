from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.liquidity import LiquidityMap

_FROZEN = ConfigDict(frozen=True, extra="ignore")

EmaCross = Literal["golden", "death"]
RsiDivergence = Literal["bullish", "bearish"]
MacdSignal = Literal["bullish", "bearish"]
VwapBias = Literal["above", "below"]
DailyTrend = Literal["up", "down", "neutral"]
OiTrend = Literal["growing", "shrinking", "neutral"]
FundingBias = Literal["long_heavy", "short_heavy", "neutral"]
CvdTrend = Literal["rising", "falling", "neutral"]
CvdPriceDivergence = Literal["bullish", "bearish"]
Direction = Literal["long", "short", "mixed"]
SmartMoneyDivergence = Literal[
    "confirms", "diverges_bullish", "diverges_bearish", "neutral"
]
PositioningRegime = Literal[
    "longs_building", "shorts_building", "shorts_covering", "longs_unwinding", "neutral"
]
SqueezeSetup = Literal["long_squeeze_primed", "short_squeeze_primed", "none"]
SpotPerpDivergence = Literal["bullish", "bearish", "none"]


class SignalDetails(BaseModel):
    model_config = _FROZEN

    atr: float
    volume_spike: bool
    bb_squeeze: bool
    ema_cross: EmaCross | None
    rsi_level: float | None
    rsi_divergence: RsiDivergence | None
    macd: MacdSignal | None
    vwap_bias: VwapBias | None
    daily_trend: DailyTrend
    near_swing: bool
    oi_change_4h_pct: float
    oi_trend: OiTrend
    oi_aggregated_trend: OiTrend = "neutral"
    funding_rate: float
    funding_bias: FundingBias
    oi_weighted_funding_bias: FundingBias
    long_short_ratio: float | None
    cvd_trend: CvdTrend
    cvd_price_divergence: CvdPriceDivergence | None
    liq_spike: bool
    top_trader_ls_ratio: float | None
    basis: float | None
    smart_money_divergence: SmartMoneyDivergence = "neutral"
    positioning_regime: PositioningRegime = "neutral"
    squeeze_setup: SqueezeSetup = "none"
    spot_perp_divergence: SpotPerpDivergence = "none"


class ScreenerResult(BaseModel):
    model_config = _FROZEN

    symbol: str
    gate_passed: bool
    score: int
    adx: float
    direction: Direction
    signals: SignalDetails
    liquidity_map: LiquidityMap | None = None


def empty_signals() -> SignalDetails:
    """Дефолтный SignalDetails — для отфильтрованных по gate и упавших на фетче символов."""
    return SignalDetails(
        atr=0.0,
        volume_spike=False,
        bb_squeeze=False,
        ema_cross=None,
        rsi_level=None,
        rsi_divergence=None,
        macd=None,
        vwap_bias=None,
        daily_trend="neutral",
        near_swing=False,
        oi_change_4h_pct=0.0,
        oi_trend="neutral",
        funding_rate=0.0,
        funding_bias="neutral",
        oi_weighted_funding_bias="neutral",
        long_short_ratio=None,
        cvd_trend="neutral",
        cvd_price_divergence=None,
        liq_spike=False,
        top_trader_ls_ratio=None,
        basis=None,
    )
