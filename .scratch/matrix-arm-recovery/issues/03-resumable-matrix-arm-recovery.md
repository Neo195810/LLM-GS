# 03 — Resume recoverable Matrix Arms

**What to build:** Operators can safely re-run a matrix after a recoverable
failure. Each retry creates a new immutable Execution for the same Matrix Arm,
retaining historical failures and provenance. Infrastructure operations receive
at most two recorded retries before terminal infrastructure failure; later
invocations can recover it, while cost exhaustion remains explicitly
`blocked-by-budget` until funds are available.

**Blocked by:** 01 — Record observable Matrix Arm states.

**Status:** complete

- [x] Re-running a recoverable arm creates a new Execution and preserves all
  older Execution records.
- [x] Infrastructure retries and terminal failures are durable and bounded;
  model-output failures are not retried as infrastructure failures.
- [x] CLI-level fake-client tests verify resume behavior, state/error reporting,
  and protocol-separated aggregation.

**Verified:** `uv run pytest tests/test_matrix.py -q` (23 passed),
`uv run mypy src/llm_gs`, and `uv run ruff check src/llm_gs tests`.
