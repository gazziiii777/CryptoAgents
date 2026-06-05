import functools
from pathlib import Path
from typing import cast

from app.services.agents.graph_builder import build_graph, load_graph_config
from app.domain.models.analysis import TechnicalReport
from app.services.agents.technical.nodes import compute_levels_node, interpret_node
from app.services.agents.technical.state import TechnicalState
from app.adapters.clients.ccxt.models import OHLCVCandle
from app.llm_gateway.service import LLMService

_GRAPH_CONFIG = Path(__file__).parent / "graph.yaml"


async def analyze_technical(
    service: LLMService,
    symbol: str,
    candles_4h: list[OHLCVCandle],
    candles_1d: list[OHLCVCandle],
) -> TechnicalReport:
    """Технический аналитик (LangGraph): свечи → детерм. уровни → LLM → TechnicalReport."""
    config = load_graph_config(_GRAPH_CONFIG)
    graph = build_graph(
        config,
        state_schema=TechnicalState,
        nodes={
            "compute_levels": compute_levels_node,
            "interpret": functools.partial(interpret_node, service=service),
        },
        conditions={},
    )
    result = await graph.ainvoke(
        TechnicalState(symbol=symbol, candles_4h=candles_4h, candles_1d=candles_1d)
    )
    return cast(TechnicalReport, result["report"])
