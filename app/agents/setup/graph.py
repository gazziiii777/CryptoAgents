import functools
import logging
from pathlib import Path
from typing import Literal, cast

from app.agents.graph_builder import build_graph, load_graph_config
from app.agents.setup.nodes import build_node, route_after_validate, validate_node
from app.agents.setup.state import SetupState
from app.llm_gateway.service import LLMService
from app.models.analysis import TechnicalReport
from app.models.setup import SetupIntent

logger = logging.getLogger(__name__)

_GRAPH_CONFIG = Path(__file__).parent / "graph.yaml"


async def build_setup(
    service: LLMService,
    direction: Literal["long", "short"],
    technical: TechnicalReport,
    current_price: float,
    atr: float,
    correction: str | None = None,
) -> SetupIntent | None:
    """SetupBuilder (LangGraph): LLM строит SetupIntent с self-correction (1 re-prompt).

    `correction` — внешняя подсказка (например «вход не разрешился, бери ближе к цене»),
    которая попадает в промпт первой попытки. None — если после ретрая сетап всё ещё не
    проходит валидацию (→ no_trade выше).
    """
    config = load_graph_config(_GRAPH_CONFIG)
    graph = build_graph(
        config,
        state_schema=SetupState,
        nodes={
            "build": functools.partial(build_node, service=service),
            "validate": validate_node,
        },
        conditions={"route_after_validate": route_after_validate},
    )
    result = await graph.ainvoke(
        SetupState(
            direction=direction,
            technical=technical,
            current_price=current_price,
            atr=atr,
            validation_error=correction,
        )
    )
    if result["validation_error"] is not None:
        logger.warning(
            "setup builder gave up after retries: %s", result["validation_error"]
        )
        return None
    return cast(SetupIntent, result["intent"])
