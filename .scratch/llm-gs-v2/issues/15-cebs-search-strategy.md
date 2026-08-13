# 15 — CEBS Search Strategy

**What to build:** Run CEBS as the final initial replaceable V2 Search Strategy, with the same experiment contracts, memory provenance, protocol rules, and budget accounting as Hill Climbing and CEM.

**Blocked by:** 14 — CEM Search Strategy.

**Status:** blocked

**Acceptance criteria:**

- [ ] CEBS can be selected in a validated Experiment Specification and completes through the standard CLI.
- [ ] CEBS preserves V2 Candidate Program, Attempt, memory, budget, and final-selection semantics.
- [ ] Deterministic fake-client coverage proves CEBS can use each configured failure strategy without bypassing shared contracts.
