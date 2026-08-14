# 03 — Resume recoverable Matrix Arms

**What to build:** Operators can safely re-run a matrix after a recoverable
failure. Each retry creates a new immutable Execution for the same Matrix Arm,
retaining historical failures and provenance. Infrastructure operations receive
at most two recorded retries before terminal infrastructure failure; later
invocations can recover it, while cost exhaustion remains explicitly
`blocked-by-budget` until funds are available.

**Blocked by:** 01 — Record observable Matrix Arm states.

**Status:** ready-for-agent

- [ ] Re-running a recoverable arm creates a new Execution and preserves all
  older Execution records.
- [ ] Infrastructure retries and terminal failures are durable and bounded;
  model-output failures are not retried as infrastructure failures.
- [ ] CLI-level fake-client tests verify resume behavior, state/error reporting,
  and protocol-separated aggregation.
