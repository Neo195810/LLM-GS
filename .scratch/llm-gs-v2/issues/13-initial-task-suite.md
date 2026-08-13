# 13 — FourCorners, DoorKey, and RedBlueDoor task suite

**What to build:** Extend the established V2 experiment boundary beyond CleanHouse to Karel FourCorners and MiniGrid DoorKey and RedBlueDoor, each with deterministic adapter behavior, Task-owned outcome semantics, evidence, state features, and Seed Suites.

**Blocked by:** 12 — Recovery, reporting, and self-verifying export.

**Status:** blocked

**Acceptance criteria:**

- [ ] Each Task runs through the same V2 DSL, evaluation, evidence, budget, and reporting boundary used by CleanHouse.
- [ ] Each Task supplies versioned Outcome Classifier, Normalized Progress, Failure Reasons, State Feature Extractor, and deterministic replay coverage.
- [ ] Fixed-program adapter equivalence remains demonstrable for each added Task.
- [ ] The initial benchmark contains only CleanHouse, FourCorners, DoorKey, and RedBlueDoor.
