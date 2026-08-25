# Program Call Limit and Crash Classification

**Status:** approved for implementation

## Problem Statement

V1 Karel, DoorKey, and RedBlueDoor evaluation must enforce `max_calls=10` as
an immediate execution policy boundary. The existing runtime can allow work to
continue after a program-call limit is exceeded and conflates policy stops,
stalled programs, invalid actions, normal MiniGrid termination, and unexpected
runtime failures under a generic crash signal. This obscures evaluation
evidence and can misclassify candidates.

## Scope

- Cover every V1 runtime: Karel, DoorKey, and RedBlueDoor.
- Keep `max_calls=10`; do not raise it to mask the defect.
- Add a dedicated `ProgramCallLimitExceeded` exception solely for an expected
  policy execution stop.
- Apply identical call-limit semantics in Karel `BaseEnvironment` and MiniGrid
  `ProgramWrapper`: the first `N` action or predicate calls execute; the
  attempted `(N + 1)`th call records `call_limit_exhausted` and raises before
  executing or changing world state. Record `program_call_count=N` and
  `attempted_program_call_count=N+1`.
- Make `evaluate_program()` catch only `ProgramCallLimitExceeded` to end
  evaluation. Propagate every other exception.
- Classify repeated DSL state as `stalled_policy`, invalid actions as
  `invalid_action`, and preserve `is_crashed()` compatibility while adding a
  readable stop reason. A normally terminated MiniGrid episode must stop
  evaluation without becoming a crash.
- Apply this behavior to actions, boolean features, integer features, and
  indexed actions.
- Have Karel, DoorKey, and RedBlueDoor adapters report
  `call_limit_exhausted`, `stalled_policy`, `invalid_action`, or
  `environment_crash` only for an unknown runtime failure. Preserve `success`
  and existing `partial_completion` behavior for normal outcomes.
- Add executed and attempted program-call counts plus stop reason to evaluation
  evidence. Add aggregated `failure_reasons` to candidate-admission audits,
  including development-gated runs without held-out evidence.

## Constraints

- Do not change the YAML schema, prompt, admission criterion, or
  `EpisodeResult` outcome set.
- Preserve ADR 0015's evidence-linked diagnostic flow.
- Preserve ADR 0021 deterministic V1 replay/equivalence: fixed DSL programs
  with identical task seeds and limits must match in terminal state, reward,
  crash status, and executed program-call count.
- Do not run a paid live pilot automatically.

## Acceptance Criteria

- With `max_calls=2`, the first two action or predicate calls execute; the
  third attempt stops immediately without an action, predicate, or world-state
  side effect.
- A limit stop reports `program_call_count=2`,
  `attempted_program_call_count=3`, and
  `failure_reason=call_limit_exhausted`.
- Nested `REPEAT`, `WHILE`, and `IF/ELSE` constructs cannot continue after the
  exception.
- A repeated-state loop is `stalled_policy`, not `call_limit_exhausted`.
- Normal MiniGrid termination does not produce a policy crash; a successful
  candidate remains `success`.
- An unexpected Python/runtime exception is not swallowed by the limit handler.
- Deterministic DoorKey, RedBlueDoor, and Karel replay/equivalence tests pass.
- A failed development-admission report aggregates failures by
  `failure_reasons`.
- The following verification passes:

  ```sh
  uv run pytest tests/test_minigrid_door_key.py tests/test_minigrid_red_blue_door.py tests/test_v1_adapter_equivalence.py tests/test_matrix.py -q
  uv run mypy src/llm_gs
  uv run ruff check src/llm_gs tests
  ```

## Deferred Live-Pilot Check

After explicit user approval, a manual live pilot must show any limit failure
with at most 10 executed calls and exactly 11 attempted calls; it must not show
44 or 119 calls, and its report must distinguish limit, stall, and other
failures. `admitted_candidate_count > 0` is not required: the repository has
no DoorKey success reference policy. If call budget remains exhausted after
this repair, create a separate calibration ticket instead of increasing the
limit.
