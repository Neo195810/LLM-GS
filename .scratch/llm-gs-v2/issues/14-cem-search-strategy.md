# 14 — CEM Search Strategy

**What to build:** Run CEM as a replaceable V2 Search Strategy across the initial Task suite, sharing the same Evaluator, failure-handling strategies, Seed Suites, Memory Snapshot rules, and accounting boundary as Hill Climbing.

**Blocked by:** 13 — FourCorners, DoorKey, and RedBlueDoor task suite.

**Status:** blocked

**Acceptance criteria:**

- [ ] CEM can be selected in a validated Experiment Specification and executes end to end through the standard CLI.
- [ ] CEM preserves Attempt lineage, Evaluation/Model Budget accounting, final-candidate selection, and protocol isolation.
- [ ] Paired fake-client experiments verify deterministic integration without coupling CEM to orchestrator internals.
