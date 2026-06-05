from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EdgeConfig(BaseModel):
    """Ребро графа из config.yaml.

    Либо прямое (`to`), либо условное (`condition` + `path_map`) — ровно одно из двух.
    `__start__`/`__end__` — служебные узлы START/END LangGraph.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    from_node: str = Field(alias="from", description="Узел-источник ребра")
    to: str | None = Field(
        default=None, description="Узел-приёмник для безусловного ребра"
    )
    condition: str | None = Field(
        default=None, description="Имя функции-роутера в реестре conditions"
    )
    path_map: dict[str, str] | None = Field(
        default=None, description="Карта результат-роутера → узел для условного ребра"
    )

    @model_validator(mode="after")
    def _exactly_one_edge_kind(self) -> Self:
        is_direct = (
            self.to is not None and self.condition is None and self.path_map is None
        )
        is_conditional = (
            self.to is None and self.condition is not None and self.path_map is not None
        )
        if not (is_direct or is_conditional):
            raise ValueError(
                f"edge from {self.from_node!r} must define either 'to' alone or "
                "both 'condition' and 'path_map' alone"
            )
        return self
