from pydantic import BaseModel, ConfigDict

from app.services.agents.models.edge_config import EdgeConfig


class GraphConfig(BaseModel):
    """Декларативная топология LangGraph-графа (config.yaml)."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    nodes: list[str]
    edges: list[EdgeConfig]
