# 03 — CleanHouse evaluation contract

**What to build:** Run real Karel CleanHouse Candidate Programs through the V2 DSL and Evaluator contract, producing versioned Episode Evaluations, Task-specific Attempt Outcomes, Normalized Progress, Failure Type/Reason, deterministic state features, and Execution Summaries under per-episode Evaluation Budget accounting.

**Blocked by:** 02 — V1 adapter deterministic equivalence.

**Status:** done

**Acceptance criteria:**

- [x] A valid CleanHouse DSL Candidate Program can be evaluated over seeded worlds through the V2 execution boundary. Verified: `src/llm_gs/execution.py:169-182` (`CleanHouseEvaluator.evaluate`), `tests/test_v1_adapter_equivalence.py:73-83`.
- [x] Every evaluation produces inspectable outcome classification, progress, failure evidence, and deterministic replay information. Verified: `src/llm_gs/contracts.py:118-128` (`EpisodeResult`), `src/llm_gs/v1_adapter.py:72-150`, `tests/test_v1_adapter_equivalence.py:86-101`.
- [x] Policy Crash, Invalid Program, and Evaluation Error remain distinct from one another and from success/partial completion. Verified: `src/llm_gs/contracts.py:119-121` (5-value outcome Literal), `src/llm_gs/v1_adapter.py:140-148`, `tests/test_v1_adapter_equivalence.py:86-101`.
- [x] Budget accounting is per Episode Evaluation and cannot exceed the resolved limit. Verified: `src/llm_gs/execution.py:580-583`, exercised in `tests/test_matrix.py:142-175`.
