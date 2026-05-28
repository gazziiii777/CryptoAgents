from typing import Literal

from pydantic import BaseModel

from app.models.analysis import TechnicalReport
from app.models.setup import SetupIntent


class SetupState(BaseModel):
    """State LangGraph-графа SetupBuilder (build → validate → retry/end)."""

    direction: Literal["long", "short"]
    technical: TechnicalReport
    current_price: float
    atr: float
    intent: SetupIntent | None = None
    validation_error: str | None = None
    attempts: int = 0
