from typing import Literal

from pydantic import BaseModel

from app.domain.models.analysis import TechnicalReport
from app.domain.models.setup import SetupIntent


class SetupState(BaseModel):
    """State LangGraph-графа SetupBuilder (build → validate → retry/end)."""

    direction: Literal["long", "short"]
    technical: TechnicalReport
    current_price: float
    atr: float
    intent: SetupIntent | None = None
    validation_error: str | None = None
    attempts: int = 0
