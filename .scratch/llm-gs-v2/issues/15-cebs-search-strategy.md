# 15 — CEBS Search Strategy

**What to build:** Run CEBS as the final initial replaceable V2 Search Strategy, with the same experiment contracts, memory provenance, protocol rules, and budget accounting as Hill Climbing and CEM.

**Blocked by:** 14 — CEM Search Strategy.

**Status:** done

**Acceptance criteria:**

- [x] CEBS can be selected in a validated Experiment Specification and completes through the standard CLI. Verified: `docs/research/complete-ablation-matrix-report.json` — `cebs` arms completed via `llm-gs matrix run`.
- [x] CEBS preserves V2 Candidate Program, Attempt, memory, budget, and final-selection semantics. Verified: `tests/test_search.py::test_cebs_selects_elites_and_records_versioned_selection_provenance`.
- [x] Deterministic fake-client coverage proves CEBS can use each configured failure strategy without bypassing shared contracts. Verified: `tests/test_search.py::test_cebs_resolves_through_the_versioned_search_strategy_contract`, and CEBS x all 4 failure strategies completed in the matrix run.
