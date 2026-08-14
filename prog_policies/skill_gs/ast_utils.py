from __future__ import annotations

from typing import Any

from prog_policies.base import dsl_nodes


def node_to_ast_dict(node: dsl_nodes.BaseNode | None, dsl) -> dict[str, Any] | None:
    """Serialize the existing DSL node tree into a JSON-friendly structure."""

    if node is None:
        return None

    data: dict[str, Any] = {
        "node_type": type(node).__name__,
        "dsl_source": dsl.parse_node_to_str(node),
    }
    if hasattr(node, "name"):
        data["name"] = node.name
    if getattr(node, "value", None) is not None:
        data["value"] = node.value
    if hasattr(node, "object"):
        data["object"] = node.object
    if hasattr(node, "color"):
        data["color"] = node.color
    if node.children:
        data["children"] = [node_to_ast_dict(child, dsl) for child in node.children]
    return data


def dsl_source_to_ast_dict(dsl_source: str, dsl) -> dict[str, Any]:
    node = dsl.parse_str_to_node(dsl_source)
    return node_to_ast_dict(node, dsl) or {}


def root_nonterminal_for(dsl_source: str, dsl) -> str:
    return type(dsl.parse_str_to_node(dsl_source)).__name__
