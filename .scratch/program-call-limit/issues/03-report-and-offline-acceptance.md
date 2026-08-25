# 03 — Report failure distributions and verify offline acceptance

**What to build:** Surface aggregate failure reasons in development admission
audits and complete the deterministic offline acceptance suite for the
reason-aware execution change.

**Blocked by:** 02 — Classify adapter failures from stop reasons.

**Status:** blocked

- [ ] Add `failure_reasons` counts to candidate-admission audit output, even
  when development gating produces no held-out evidence.
- [ ] Confirm reports distinguish limit exhaustion, stalled policies, invalid
  actions, and unexpected environment crashes without schema migration.
- [ ] Run and record the required offline pytest, mypy, and ruff checks.
- [ ] Confirm fixed-program V1 replay/equivalence remains deterministic for
  identical DSL, task seeds, and limits, per ADR 0021.
- [ ] Do not execute a paid live pilot. Document its explicit-approval manual
  check and open a separate calibration ticket if the budget is still exhausted.

**Acceptance:** A development-admission failure report contains aggregated
`failure_reasons`, and all offline checks in `../spec.md` pass.
