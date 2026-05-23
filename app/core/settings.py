from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", frozen=True
    )

    EXCHANGE_ID: str = "binance"
    QUOTE_CURRENCY: str = "USDT"

    UNIVERSE_MIN_VOLUME_USD: float = 5_000_000

    SCREENER_4H_LIMIT: int = 200
    SCREENER_1D_LIMIT: int = 100

    FUNDING_HISTORY_LIMIT: int = 21
    OI_HISTORY_LIMIT: int = 50
    LS_RATIO_LIMIT: int = 50
    SCREENER_LS_RATIO_LIMIT: int = 1
    CVD_CANDLES: int = 24

    HTTP_TIMEOUT_S: int = 10

    ADX_GATE_MIN: float = 20.0
    SCREENER_MIN_SCORE: int = 4
    SCREENER_TOP_N: int = 15
    SCREENER_CONCURRENCY: int = 15
    DIRECTION_VOTE_THRESHOLD: int = 3

    VOLUME_SPIKE_MULTIPLIER: float = 1.5
    BB_SQUEEZE_THRESHOLD: float = 0.02
    NEAR_SWING_ATR_MULT: float = 0.5
    NEAR_SWING_WINDOW: int = 50
    RSI_OVERBOUGHT: float = 70.0
    RSI_OVERSOLD: float = 30.0

    OI_TREND_MIN_PCT: float = 0.15
    OI_CHANGE_4H_SCORE_PCT: float = 0.05
    FUNDING_RATE_HIGH: float = 0.0015
    FUNDING_RATE_LOW: float = -0.0005
    LS_RATIO_HIGH: float = 3.3
    LS_RATIO_LOW: float = 0.55
    BASIS_CONTANGO_THRESHOLD: float = 0.05

    LIQ_SPIKE_WINDOW: int = 8
    LIQ_SPIKE_MULTIPLIER: float = 3.0

    COINGLASS_STARTUP_PLAN: bool = False
    COINGLASS_STANDARD_PLAN: bool = False
    COINGLASS_PROFESSIONAL_PLAN: bool = False

    COINGECKO_API_KEY: str = ""
    COINGLASS_API_KEY: str = ""
    LUNARCRUSH_API_KEY: str = ""

    LUNARCRUSH_WHATSUP_ENABLED: bool = False

    LUNARCRUSH_LIST_LIMIT: int = 1000
    LUNARCRUSH_SENTIMENT_BULLISH_THRESHOLD: float = 60.0
    LUNARCRUSH_SENTIMENT_BEARISH_THRESHOLD: float = 40.0
    LUNARCRUSH_CONTRARIAN_HIGH: float = 85.0
    LUNARCRUSH_CONTRARIAN_LOW: float = 15.0

    LUNARCRUSH_ATTENTION_RATIO_SPIKE: float = 3.0
    LUNARCRUSH_ATTENTION_RATIO_NORMAL: float = 0.5
    LUNARCRUSH_BASELINE_DAYS: int = 7

    LUNARCRUSH_POSTS_LIMIT: int = 30
    LUNARCRUSH_NEWS_LIMIT: int = 10
    LUNARCRUSH_INFLUENCER_FOLLOWERS_THRESHOLD: int = 100_000

    LUNARCRUSH_POST_SENTIMENT_BULLISH: float = 3.5
    LUNARCRUSH_POST_SENTIMENT_BEARISH: float = 2.5

    NEWS_FRESH_CATALYST_WINDOW_H: int = 24
    NEWS_TOP_K: int = 5

    LLM_QUICK_MODEL: str = "claude-haiku-4-5"
    LLM_DEEP_MODEL: str = "claude-sonnet-4-6"


settings = Settings()
