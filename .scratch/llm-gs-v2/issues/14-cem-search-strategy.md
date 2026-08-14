# 14 — CEM Search Strategy

**What to build:** Run CEM as a replaceable V2 Search Strategy across the initial Task suite, sharing the same Evaluator, failure-handling strategies, Seed Suites, Memory Snapshot rules, and accounting boundary as Hill Climbing.

**Blocked by:** 13 — FourCorners, DoorKey, and RedBlueDoor task suite.

**Status:** done

**Acceptance criteria:**

- [x] CEM can be selected in a validated Experiment Specification and executes end to end through the standard CLI. Verified: `docs/research/complete-ablation-matrix-report.json` — `cem` arms completed via `llm-gs matrix run`.
- [x] CEM preserves Attempt lineage, Evaluation/Model Budget accounting, final-candidate selection, and protocol isolation. Verified: `tests/test_search.py::test_cem_selects_the_best_development_candidate_and_records_elites`.
- [x] Paired fake-client experiments verify deterministic integration without coupling CEM to orchestrator internals. Verified: `tests/test_search.py::test_search_strategy_registry_does_not_depend_on_task_or_orchestrator`.
