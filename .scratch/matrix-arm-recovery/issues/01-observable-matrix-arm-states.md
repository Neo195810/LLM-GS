# 01 — Record observable Matrix Arm states

**What to build:** Every preregistered Matrix Arm has a durable, observable
lifecycle. A matrix run records `pending`, `running`, `completed`,
`development-gated`, `model-output-failed`, `infrastructure-failed`, or
`blocked-by-budget` plus a bounded error summary, instead of silently omitting
failed arms. Reports show these states explicitly and only completed arms enter
protocol-specific Frozen or Online success rates and confidence intervals.

**Blocked by:** None — can start immediately.

**Status:** complete

- [x] A proposal, parser, execution, infrastructure, or budget failure leaves
  a durable Matrix Arm state and bounded diagnostic record.
- [x] No Matrix Arm is silently skipped by the CLI runner.
- [x] Frozen and Online reporting excludes non-completed arms from statistics
  while accounting for them explicitly.

**Verified:** `uv run pytest tests/test_matrix.py -q` (23 passed).

**Reporting note:** `development-gated` is an explicit admission outcome and
is excluded from protocol statistics.
