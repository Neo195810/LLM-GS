# 06 — Unify bracket-matching helpers

**What to build:** `prog_policies/base/dsl.py` currently has two independent implementations for finding a delimiter's matching close token: `_matching_close` (offset-based, used by `_validate_external_tokens`/`_validate_boolean_expression`) and `_find_close_token` (assert-based, used by `parse_str_list_to_node`). They encode the same depth-counting logic twice, so a bug fix or edge-case change to one can silently miss the other. Consolidate on a single implementation that both the validation pass and the parse pass call, with identical matching behavior to what's there today.

**Blocked by:** None — can start immediately

**Status:** completed

- [x] `parse_str_list_to_node` no longer calls `_find_close_token`; it (directly or indirectly) uses the same matching logic as `_validate_external_tokens`/`_validate_boolean_expression`.
- [x] The old `_find_close_token` function is removed once nothing calls it (or is reduced to a thin wrapper only if a genuinely distinct call signature is unavoidable — prefer full removal).
- [x] Matching behavior is unchanged for all delimiter pairs (`m`, `c`, `w`, `i`, `e`, `r`, `h`) in both the Karel and MiniGrid dialects.
- [x] Full test suite passes with no new failures beyond the pre-existing PATH-related ones; no new ruff violations introduced.
- [x] No change to `DSLParseError` messages/contract or to any public parsing behavior — this is an internal dedup only.

`_find_close_token` also had a second call site in `prog_policies/minigrid/dsl.py`'s own `parse_str_list_to_node` (not just the base class) — updated in the same pass, since the function it imported was being removed entirely.
