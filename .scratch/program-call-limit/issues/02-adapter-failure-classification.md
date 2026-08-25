# 02 — Classify adapter failures from stop reasons

**What to build:** Update the Karel, DoorKey, and RedBlueDoor V1 adapters to
turn runtime stop reasons into unambiguous evaluation evidence while preserving
the existing outcome schema.

**Blocked by:** 01 — Add reason-aware program-call stop semantics.

**Status:** blocked

- [ ] Map stop reasons to `call_limit_exhausted`, `stalled_policy`, and
  `invalid_action`; reserve `environment_crash` for unknown runtime failures.
- [ ] Preserve `success` for completed episodes and existing
  `partial_completion` behavior for normal incomplete termination.
- [ ] Include executed and attempted program-call counts and stop reason in
  evaluation evidence.
- [ ] Add deterministic adapter regressions, including normal MiniGrid
  termination and propagation of unexpected Python/runtime exceptions.

**Acceptance:** DoorKey, RedBlueDoor, and Karel emit the evidence and failure
classification specified in `../spec.md`, without changing the
`EpisodeResult` outcome set.
