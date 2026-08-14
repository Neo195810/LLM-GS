# 05 — CleanHouse Hill Climbing with Regenerate

**What to build:** Deliver an executable CleanHouse experiment in which Hill Climbing explores Candidate Programs with the Regenerate failure strategy, uses resolved Evaluation and Model Budgets, and remains reproducible through the CLI with a fake OpenAI client.

**Blocked by:** 03 — CleanHouse evaluation contract; 04 — OpenAI structured role boundary.

**Status:** done

**Acceptance criteria:**

- [x] A validated Experiment Specification can execute CleanHouse Hill Climbing with Regenerate end to end through the CLI. Verified: `src/llm_gs/execution.py:522-612` (`_execute_reflect`, regenerate path), `tests/test_matrix.py:142-175`.
- [x] Failed candidates return to Global Search without creating synthetic Repair Cycles. Verified: `src/llm_gs/execution.py:593-612` (regenerate proposes without `cycle.repair()`), `tests/test_matrix.py:49-54`.
- [x] Candidate and Episode counts, model usage, Attempt Outcomes, and budget exhaustion are observable in the persisted result. Verified: `src/llm_gs/contracts.py:199-210` (`ExperimentReport`), `src/llm_gs/execution.py:678-689`, `tests/test_matrix.py:162-175`.
- [x] The fake-client experiment is deterministic and covered in default CI. Verified: `src/llm_gs/execution.py:65-90` (`FakeOpenAIClient`), `tests/test_matrix.py:142-175` (48/48 deterministic arms).
