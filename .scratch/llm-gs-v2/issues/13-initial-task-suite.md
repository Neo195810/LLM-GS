# 13 — FourCorners, DoorKey, and RedBlueDoor task suite

**What to build:** Extend the established V2 experiment boundary beyond CleanHouse to Karel FourCorners and MiniGrid DoorKey and RedBlueDoor, each with deterministic adapter behavior, Task-owned outcome semantics, evidence, state features, and Seed Suites.

**Blocked by:** 12 — Recovery, reporting, and self-verifying export.

**Status:** done

**Acceptance criteria:**

- [x] Each Task runs through the same V2 DSL, evaluation, evidence, budget, and reporting boundary used by CleanHouse. Verified: `docs/research/complete-ablation-matrix-report.json` — all 4 tasks completed through the shared matrix/reporting pipeline (48/48 arms, 0 missingness).
- [x] Each Task supplies versioned Outcome Classifier, Normalized Progress, Failure Reasons, State Feature Extractor, and deterministic replay coverage. Verified: `tests/test_minigrid_door_key.py`, `tests/test_minigrid_red_blue_door.py`, `tests/test_v1_adapter_equivalence.py` (versioned evidence, replay, normalized progress).
- [x] Fixed-program adapter equivalence remains demonstrable for each added Task. Verified: `tests/test_v1_adapter_equivalence.py::test_v1_adapter_matches_deterministic_v1_execution` covers CleanHouse, FourCorners, RedBlueDoor; `tests/test_minigrid_door_key.py::test_door_key_adapter_matches_the_v1_minigrid_runtime` covers DoorKey.
- [x] The initial benchmark contains only CleanHouse, FourCorners, DoorKey, and RedBlueDoor. Verified: `src/llm_gs/contracts.py` `TaskSpecification`/`ExperimentManifest` task Literal is exactly these 4 (TextWorldPilot is a separate, explicitly non-formal-benchmark pilot).
