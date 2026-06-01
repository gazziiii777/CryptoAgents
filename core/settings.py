from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.constants.llm import (
    DEEP_MODEL_BY_PROVIDER,
    QUICK_MODEL_BY_PROVIDER,
    LLMProvider,
)
from core.constants.markets import QUOTE_CURRENCY as _QUOTE_CURRENCY


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", frozen=True
    )

    EXCHANGE_ID: str = "binance"
    QUOTE_CURRENCY: str = _QUOTE_CURRENCY

    DB_HOST: str = "db"
    DB_PORT: int = 3306
    DB_USER: str = "tradingagents"
    DB_PASSWORD: str = "tradingagents"
    DB_NAME: str = "tradingagents"
    DB_RESEARCH_NAME: str = "research"
    DB_POOL_SIZE: int = Field(default=5, ge=1, le=50)
    DB_MAX_OVERFLOW: int = Field(default=10, ge=0, le=100)
    DB_POOL_RECYCLE_S: int = Field(default=3600, ge=60, le=86400)

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        return (
            f"mysql+aiomysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
        )

    @computed_field
    @property
    def RESEARCH_DATABASE_URL(self) -> str:
        return (
            f"mysql+aiomysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_RESEARCH_NAME}?charset=utf8mb4"
        )

    UNIVERSE_MIN_VOLUME_USD: float = 5_000_000

    SCREENER_4H_LIMIT: int = 200
    SCREENER_1D_LIMIT: int = 100

    FUNDING_HISTORY_LIMIT: int = 21
    OI_HISTORY_LIMIT: int = 50
    LS_RATIO_LIMIT: int = 50
    SCREENER_LS_RATIO_LIMIT: int = 1
    SCREENER_BASIS_LIMIT: int = 1
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
    RSI_SHORT_FLOOR: float = Field(default=25.0, ge=0.0, le=100.0)
    RSI_LONG_CEIL: float = Field(default=75.0, ge=0.0, le=100.0)

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
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

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
    PUMP_INFLUENCER_MIN: int = Field(default=3, ge=1, le=100)

    LLM_PROVIDER: LLMProvider = LLMProvider.OPENAI

    @computed_field
    @property
    def LLM_QUICK_MODEL(self) -> str:
        return QUICK_MODEL_BY_PROVIDER[self.LLM_PROVIDER]

    @computed_field
    @property
    def LLM_DEEP_MODEL(self) -> str:
        return DEEP_MODEL_BY_PROVIDER[self.LLM_PROVIDER]

    LLM_DAILY_BUDGET_USD: float = Field(default=5.0, ge=0.0, le=1000.0)
    LLM_MAX_OUTPUT_TOKENS: int = Field(default=4096, ge=256, le=32000)
    LLM_MAX_RETRIES: int = Field(default=2, ge=0, le=5)
    LLM_TEMPERATURE: float = Field(default=0.2, ge=0.0, le=2.0)
    LLM_TIMEOUT_S: float = Field(default=60.0, ge=5.0, le=600.0)

    CONFLUENCE_GATE: float = Field(default=0.50, ge=0.0, le=1.0)
    CONFIDENCE_SHRINKAGE: float = Field(default=0.75, ge=0.1, le=1.0)
    RISK_REWARD_MIN: float = Field(default=1.5, ge=1.0, le=10.0)
    FUNDING_COST_MAX_PCT: float = Field(default=0.01, ge=0.0, le=1.0)
    FUNDING_EXTREME_PCT: float = Field(default=0.0030, gt=0.0, le=1.0)

    DEFAULT_ACCOUNT_NAME: str = "paper"
    DEFAULT_INITIAL_BALANCE: int = Field(default=2000, ge=1)
    RISK_PER_TRADE_MIN_PCT: float = Field(default=0.005, gt=0.0, le=0.1)
    RISK_PER_TRADE_MAX_PCT: float = Field(default=0.02, gt=0.0, le=0.2)
    MARGIN_PER_TRADE_MIN_PCT: float = Field(default=0.03, gt=0.0, le=0.5)
    MARGIN_PER_TRADE_MAX_PCT: float = Field(default=0.06, gt=0.0, le=1.0)
    MAX_CONCURRENT_POSITIONS: int = Field(default=5, ge=1, le=50)
    MAX_SAME_DIRECTION: int = Field(default=2, ge=1, le=50)
    MAX_LEVERAGE: int = Field(default=10, ge=1, le=125)
    DRAWDOWN_HALT_PCT: float = Field(default=0.10, gt=0.0, le=1.0)
    FUNDING_KILL_SWITCH_PCT: float = Field(default=0.0025, gt=0.0, le=1.0)
    TAKER_FEE_RATE: float = Field(default=0.0005, ge=0.0, le=0.01)
    BREAKEVEN_TRIGGER_R: float = Field(default=1.0, gt=0.0, le=10.0)
    TRAIL_ACTIVATION_R: float = Field(default=1.5, gt=0.0, le=10.0)
    TRAIL_DISTANCE_R: float = Field(default=1.0, gt=0.0, le=10.0)
    EXIT_TIMEFRAME: str = "15m"
    EXIT_CANDLE_LIMIT: int = Field(default=1000, ge=1, le=1500)

    TELEGRAM_BOT_TOKEN: str | None = None
    TELEGRAM_CHAT_ID: str | None = None

    @computed_field
    @property
    def TELEGRAM_ENABLED(self) -> bool:
        return bool(self.TELEGRAM_BOT_TOKEN and self.TELEGRAM_CHAT_ID)


settings = Settings()
