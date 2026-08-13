from __future__ import annotations

import hashlib

from prog_policies.karel.dsl import KarelDSL


def normalized_ast_hash(source: str) -> str:
    """Hash the parser's canonical Karel AST serialization, not source formatting."""
    dsl = KarelDSL()  # type: ignore[no-untyped-call]
    canonical_source = dsl.parse_node_to_str(dsl.parse_str_to_node(source))
    return hashlib.sha256(canonical_source.encode("utf-8")).hexdigest()
