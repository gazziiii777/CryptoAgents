from dataclasses import dataclass

from app.domain.models.setup import FinalSignal


@dataclass
class FillResult:
    final_signal: FinalSignal | None
    reason: str
