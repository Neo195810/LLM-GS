# 06 — CleanHouse Reflect repair cycle

**What to build:** Add the Reflect strategy at the same post-failure boundary as Regenerate, so a failed CleanHouse Candidate Program receives evidence-linked Diagnosis and a complete DSL repair under a bounded Repair Cycle.

**Blocked by:** 05 — CleanHouse Hill Climbing with Regenerate.

**Status:** blocked

**Acceptance criteria:**

- [ ] Diagnosis cites Evaluation Evidence, separates observations from hypotheses, and persists its link to the failed Program Attempt.
- [ ] Repair returns a complete DSL Candidate Program and Repair Intent; the system records the actual parent-child AST difference.
- [ ] Configured 0/1/3 repair limits and early stops for unchanged AST, repeated unimproved failure, and budget exhaustion are enforced.
- [ ] Regenerate and Reflect remain comparable through identical paired seeds and total budgets.
