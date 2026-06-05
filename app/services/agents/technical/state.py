from pydantic import BaseModel

from app.domain.models.analysis import TechnicalReport
from app.services.agents.technical.models import TechnicalFacts
from app.adapters.clients.ccxt.models import OHLCVCandle


class TechnicalState(BaseModel):
    """State LangGraph-графа технического аналитика."""

    symbol: str
    candles_4h: list[OHLCVCandle]
    candles_1d: list[OHLCVCandle]
    facts: TechnicalFacts | None = None
    report: TechnicalReport | None = None
