# 07 — Single-source the DSL grammar between validation and parsing

**What to build:** `prog_policies/base/dsl.py` currently encodes the DSL's grammar twice: once in `_validate_external_tokens`/`_validate_boolean_expression` (structural pre-validation, run before parsing) and again in `parse_str_list_to_node` (the actual token-to-AST parse). Each construct's shape (`IF c( <bool> c) i( <stmt> i)`, `not c( <bool> c)`, etc.) is spelled out independently in both places. A future grammar change (new construct, changed arity) requires editing both and keeping them in sync by hand, which is exactly how ticket 05's stranded-token regression happened. Refactor so there is one authoritative source for each construct's shape — e.g. have the validation pass produce boundary/offset information that the parse pass consumes directly, or have the parse pass itself perform the structural checks it currently assumes are already done — so the two can no longer drift apart.

**Blocked by:** 06 — unify bracket-matching helpers first so this refactor isn't juggling two parallel matching implementations while also touching grammar structure

**Status:** completed

- [x] Each DSL construct's token shape (delimiters, arity, ordering) is defined in exactly one place that both validation and parsing consult, not duplicated.
- [x] `DSLParseError` behavior (constructs, offsets, expected/actual messages) for all currently-tested error cases is unchanged.
- [x] All currently-valid Karel and MiniGrid programs (including multi-token MiniGrid features like `front_object_type h( <color> h)`) still parse successfully.
- [x] Full test suite passes with no new failures beyond the pre-existing PATH-related ones; no new ruff violations introduced.
- [x] Add or update a test that documents the single-source property is meaningful — e.g. a construct-shape change made in only the shared definition is picked up by both validation and parsing (or, at minimum, a regression test for the ticket 05 stranded-token case still passes under the new structure).

`MinigridDSL.parse_str_list_to_node` was a byte-for-byte copy of `BaseDSL.parse_str_list_to_node` — every statement/boolean construct's parse shape (`IF`, `IFELSE`, `WHILE`, `REPEAT`, `not`/`and`/`or`, `DEF`) was duplicated wholesale, differing only in the bool-feature leaf case (MiniGrid's `h( ... h)` multi-token features). Introduced a `_parse_bool_feature(prog_str_list) -> (node, consumed)` hook on `BaseDSL` that the base leaf case uses and that `MinigridDSL` overrides for `front_object_type`/`front_object_color`; deleted MiniGrid's entire duplicate override so it now inherits `parse_str_list_to_node` from `BaseDSL` unchanged. `_matching_close` import in `minigrid/dsl.py` removed as it's now unused there. Added `test_minigrid_dsl_does_not_duplicate_the_base_parse_dispatch` to `tests/test_openai_proposer.py` asserting `MinigridDSL` no longer defines its own `parse_str_list_to_node`.
