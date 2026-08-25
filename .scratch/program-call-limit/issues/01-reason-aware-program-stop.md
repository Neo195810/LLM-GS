# 01 — Add reason-aware program-call stop semantics

**What to build:** Introduce the dedicated policy-stop exception and make V1
Karel and MiniGrid execution stop immediately and consistently at the program
call limit, while recording a compatibility-safe, readable stop reason.

**Blocked by:** none.

**Status:** ready-for-agent

- [ ] Add `ProgramCallLimitExceeded`, used only for the expected policy limit
  stop.
- [ ] In `BaseEnvironment` and `ProgramWrapper`, allow exactly `N` action or
  predicate calls; on attempt `N+1`, set `call_limit_exhausted`, preserve the
  executed count, record the attempted count, and raise before any side effect.
- [ ] Ensure all action, boolean feature, integer feature, and indexed-action
  paths use those semantics.
- [ ] Catch only the dedicated exception in `evaluate_program()`; propagate
  unexpected runtime errors.
- [ ] Distinguish `stalled_policy` and `invalid_action`; preserve
  `is_crashed()` compatibility; treat normal MiniGrid termination as normal.
- [ ] Add focused regressions for the limit boundary and nested DSL control
  flow, including no-side-effect verification.

**Acceptance:** Satisfy the runtime-stop portions of
`../spec.md`'s acceptance criteria without changing `max_calls`, YAML schema,
prompts, or admission criteria.
