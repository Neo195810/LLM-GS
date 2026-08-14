# 06 — CleanHouse Reflect repair cycle

**What to build:** Add the Reflect strategy at the same post-failure boundary as Regenerate, so a failed CleanHouse Candidate Program receives evidence-linked Diagnosis and a complete DSL repair under a bounded Repair Cycle.

**Blocked by:** 05 — CleanHouse Hill Climbing with Regenerate.

**Status:** done

**Acceptance criteria:**

- [x] Diagnosis cites Evaluation Evidence, separates observations from hypotheses, and persists its link to the failed Program Attempt. Verified: `src/llm_gs/reflection.py:21-41` (`RepairCycle.diagnose`), `src/llm_gs/contracts.py:141-146` (`Diagnosis`), `tests/test_reflection.py:10-31,48-63`.
- [x] Repair returns a complete DSL Candidate Program and Repair Intent; the system records the actual parent-child AST difference. Verified: `src/llm_gs/reflection.py:43-81` (`RepairCycle.repair`, `_ast_difference`), `src/llm_gs/contracts.py:154-161` (`RepairAttempt`), `tests/test_reflection.py:10-31`.
- [x] Configured 0/1/3 repair limits and early stops for unchanged AST, repeated unimproved failure, and budget exhaustion are enforced. Verified: `src/llm_gs/reflection.py:14-19,52-60`, `src/llm_gs/execution.py:658-661,676-677`, `tests/test_reflection.py:34-45`.
- [x] Regenerate and Reflect remain comparable through identical paired seeds and total budgets. Verified: `src/llm_gs/execution.py:522-691` (shared seed/budget scope), `src/llm_gs/contracts.py:45-56` (`SearchStrategySpecification`), `tests/test_matrix.py:25-64`.
