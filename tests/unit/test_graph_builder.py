from typing import TypedDict

import pytest
import yaml
from pydantic import ValidationError

from app.services.agents.graph_builder import build_graph
from app.services.agents.models import GraphConfig

_YAML = """
nodes:
  - start_node
  - go_b
  - go_c
edges:
  - from: __start__
    to: start_node
  - from: start_node
    condition: route
    path_map:
      TO_B: go_b
      TO_C: go_c
  - from: go_b
    to: __end__
  - from: go_c
    to: __end__
"""


class _State(TypedDict, total=False):
    choice: str
    visited: list[str]


def _start_node(state: _State) -> dict[str, list[str]]:
    return {"visited": [*state.get("visited", []), "start"]}


def _go_b(state: _State) -> dict[str, list[str]]:
    return {"visited": [*state["visited"], "b"]}


def _go_c(state: _State) -> dict[str, list[str]]:
    return {"visited": [*state["visited"], "c"]}


def _route(state: _State) -> str:
    return "TO_B" if state["choice"] == "b" else "TO_C"


_NODES = {"start_node": _start_node, "go_b": _go_b, "go_c": _go_c}
_CONDITIONS = {"route": _route}


def _build():
    config = GraphConfig.model_validate(yaml.safe_load(_YAML))
    return build_graph(
        config, state_schema=_State, nodes=_NODES, conditions=_CONDITIONS
    )


def test_conditional_routing_takes_b_branch():
    graph = _build()
    out = graph.invoke({"choice": "b", "visited": []})
    assert out["visited"] == ["start", "b"]


def test_conditional_routing_takes_c_branch():
    graph = _build()
    out = graph.invoke({"choice": "x", "visited": []})
    assert out["visited"] == ["start", "c"]


def test_missing_node_implementation_raises():
    config = GraphConfig.model_validate(yaml.safe_load(_YAML))
    with pytest.raises(ValueError, match="missing from registry"):
        build_graph(
            config,
            state_schema=_State,
            nodes={"start_node": _start_node, "go_b": _go_b},
            conditions=_CONDITIONS,
        )


def test_unknown_condition_raises():
    config = GraphConfig.model_validate(yaml.safe_load(_YAML))
    with pytest.raises(ValueError, match="condition not in registry"):
        build_graph(config, state_schema=_State, nodes=_NODES, conditions={})


def test_edge_with_both_kinds_rejected():
    with pytest.raises(ValidationError, match="must define either"):
        GraphConfig.model_validate({
            "nodes": ["a"],
            "edges": [{"from": "a", "to": "__end__", "condition": "route"}],
        })


def test_edge_with_no_kind_rejected():
    with pytest.raises(ValidationError, match="must define either"):
        GraphConfig.model_validate({"nodes": ["a"], "edges": [{"from": "a"}]})


def test_unknown_yaml_key_rejected():
    with pytest.raises(ValidationError, match="Extra inputs"):
        GraphConfig.model_validate({
            "nodes": ["a"],
            "edges": [{"form": "a", "to": "__end__"}],
        })
