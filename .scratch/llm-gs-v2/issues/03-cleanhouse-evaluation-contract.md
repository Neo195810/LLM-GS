# 03 — CleanHouse evaluation contract

**What to build:** Run real Karel CleanHouse Candidate Programs through the V2 DSL and Evaluator contract, producing versioned Episode Evaluations, Task-specific Attempt Outcomes, Normalized Progress, Failure Type/Reason, deterministic state features, and Execution Summaries under per-episode Evaluation Budget accounting.

**Blocked by:** 02 — V1 adapter deterministic equivalence.

**Status:** blocked

**Acceptance criteria:**

- [ ] A valid CleanHouse DSL Candidate Program can be evaluated over seeded worlds through the V2 execution boundary.
- [ ] Every evaluation produces inspectable outcome classification, progress, failure evidence, and deterministic replay information.
- [ ] Policy Crash, Invalid Program, and Evaluation Error remain distinct from one another and from success/partial completion.
- [ ] Budget accounting is per Episode Evaluation and cannot exceed the resolved limit.
