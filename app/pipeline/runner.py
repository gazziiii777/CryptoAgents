import logging

from app.enricher.enricher import DataEnricher
from app.llm_gateway.service import LLMService
from app.models.analysis import CandidateSignal
from app.pipeline.analysis import run_analysis
from app.pipeline.persistence import persist_signals
from app.screener.screener import run_screener
from db.engine import session_scope
from db.research.writer import record_signals

logger = logging.getLogger(__name__)


async def run_pipeline(symbol_limit: int | None = None) -> list[CandidateSignal] | None:
    """Полный прогон: screener → enricher → аналитики + агрегатор.

    Логирует финальный JSON каждой стадии (поле `result`).
    symbol_limit — ограничить юниверс топ-N пар (smoke/dev); None = полный прогон.
    Возвращает None, если скринер не дал кандидатов.
    """
    candidates = await run_screener(limit=symbol_limit)
    logger.info(
        "screener stage complete",
        extra={
            "stage": "screener",
            "candidate_count": len(candidates),
            "result": [candidate.model_dump(mode="json") for candidate in candidates],
        },
    )

    if not candidates:
        logger.warning("no screener candidates, skipping enricher")
        return None

    enrichment = await DataEnricher().enrich(candidates)
    logger.info(
        "enricher stage complete",
        extra={
            "stage": "enricher",
            "candidate_count": len(enrichment.candidates),
            "result": enrichment.model_dump(mode="json"),
        },
    )

    signals = await run_analysis(LLMService(), enrichment)
    logger.info(
        "analysis stage complete",
        extra={
            "stage": "analysis",
            "candidate_count": len(signals),
            "result": [signal.model_dump(mode="json") for signal in signals],
        },
    )

    async with session_scope() as session:
        persisted = await persist_signals(session, signals)
    logger.info(
        "persist stage complete",
        extra={"stage": "persist", "persisted": len(persisted)},
    )

    await record_signals(persisted)
    logger.info("research stage complete", extra={"stage": "research"})
    return signals
