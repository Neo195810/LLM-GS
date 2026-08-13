from __future__ import annotations

import hashlib
import re

from prog_policies.karel.dsl import KarelDSL
from prog_policies.minigrid.dsl import MinigridDSL


def normalized_ast_hash(source: str, task_name: str | None = None) -> str:
    """Hash the parser's canonical AST serialization, not source formatting."""
    source = _normalize_dsl_whitespace(source)
    if task_name == "DoorKey":
        minigrid_dsl = MinigridDSL()  # type: ignore[no-untyped-call]
        canonical_source = minigrid_dsl.parse_node_to_str(
            minigrid_dsl.parse_str_to_node(source)
        )
    elif task_name in {"CleanHouse", "FourCorners"}:
        karel_dsl = KarelDSL()  # type: ignore[no-untyped-call]
        canonical_source = karel_dsl.parse_node_to_str(karel_dsl.parse_str_to_node(source))
    else:
        try:
            karel_dsl = KarelDSL()  # type: ignore[no-untyped-call]
            canonical_source = karel_dsl.parse_node_to_str(karel_dsl.parse_str_to_node(source))
        except Exception:
            minigrid_dsl = MinigridDSL()  # type: ignore[no-untyped-call]
            canonical_source = minigrid_dsl.parse_node_to_str(
                minigrid_dsl.parse_str_to_node(source)
            )
    return hashlib.sha256(canonical_source.encode("utf-8")).hexdigest()


def _normalize_dsl_whitespace(source: str) -> str:
    source = re.sub(r"([mceirwh])\s*\(", r"\1(", source)
    source = re.sub(r"([mceirwh])\s*\)", r"\1)", source)
    return " ".join(source.split())
