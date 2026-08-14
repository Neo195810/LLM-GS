# 01 — Record observable Matrix Arm states

**What to build:** Every preregistered Matrix Arm has a durable, observable
lifecycle. A matrix run records `pending`, `running`, `completed`,
`model-output-failed`, `infrastructure-failed`, or `blocked-by-budget` plus a
bounded error summary, instead of silently omitting failed arms. Reports show
these states explicitly and only completed arms enter protocol-specific Frozen
or Online success rates and confidence intervals.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] A proposal, parser, execution, infrastructure, or budget failure leaves
  a durable Matrix Arm state and bounded diagnostic record.
- [ ] No Matrix Arm is silently skipped by the CLI runner.
- [ ] Frozen and Online reporting excludes non-completed arms from statistics
  while accounting for them explicitly.
