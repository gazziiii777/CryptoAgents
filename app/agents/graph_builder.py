from collections.abc import Callable, Mapping
from pathlib import Path

import yaml
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.models import GraphConfig

_START = "__start__"
_END = "__end__"


def load_graph_config(path: Path) -> GraphConfig:
    """Загрузить и провалидировать топологию графа из YAML-файла."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return GraphConfig.model_validate(raw)


def build_graph(
    config: GraphConfig,
    *,
    state_schema: type,
    nodes: Mapping[str, Callable[..., object]],
    conditions: Mapping[str, Callable[..., str]],
) -> CompiledStateGraph:
    """Собрать и скомпилировать StateGraph по декларативной топологии.

    nodes/conditions — реестры «имя из config.yaml → callable». Все имена, на
    которые ссылается конфиг, проверяются до сборки (fail-fast при опечатке в
    YAML), потому что в строковой топологии типизация их не ловит.
    """
    _validate_references(config, nodes, conditions)

    builder = StateGraph(state_schema)
    for name in config.nodes:
        builder.add_node(name, nodes[name])

    for edge in config.edges:
        source = START if edge.from_node == _START else edge.from_node
        if edge.to is not None:
            builder.add_edge(source, END if edge.to == _END else edge.to)
        elif edge.condition is not None and edge.path_map is not None:
            builder.add_conditional_edges(
                source, conditions[edge.condition], _resolve_path_map(edge.path_map)
            )
        else:
            raise ValueError(f"malformed edge from {edge.from_node!r}")

    return builder.compile()


def _resolve_path_map(path_map: dict[str, str]) -> dict[str, str]:
    return {key: (END if dest == _END else dest) for key, dest in path_map.items()}


def _validate_references(
    config: GraphConfig,
    nodes: Mapping[str, Callable[..., object]],
    conditions: Mapping[str, Callable[..., str]],
) -> None:
    declared = set(config.nodes)

    missing_impl = declared - set(nodes)
    if missing_impl:
        raise ValueError(
            f"nodes declared in config but missing from registry: {sorted(missing_impl)}"
        )

    for edge in config.edges:
        if edge.from_node != _START and edge.from_node not in declared:
            raise ValueError(f"edge 'from' references unknown node: {edge.from_node!r}")

        if edge.to is not None:
            if edge.to != _END and edge.to not in declared:
                raise ValueError(f"edge 'to' references unknown node: {edge.to!r}")
        elif edge.condition is not None and edge.path_map is not None:
            if edge.condition not in conditions:
                raise ValueError(f"edge condition not in registry: {edge.condition!r}")
            unknown = {
                dest
                for dest in edge.path_map.values()
                if dest != _END and dest not in declared
            }
            if unknown:
                raise ValueError(
                    f"path_map references unknown nodes: {sorted(unknown)}"
                )
