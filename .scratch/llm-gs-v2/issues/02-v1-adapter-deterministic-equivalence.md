# 02 — V1 adapter deterministic equivalence

**What to build:** Make the V1 baseline trustworthy through V2 adapters by proving that a fixed DSL program, identical Task seeds, and identical execution limits yield the same terminal state, reward, crash status, and program call count in V1 and the adapter. Model-generated text is intentionally outside this comparison.

**Blocked by:** 01 — V2 offline tracer bullet (completed).

**Status:** completed / resolved

**Acceptance criteria:**

- [x] Deterministic equivalence cases cover the initial Karel and MiniGrid adapter surfaces with fixed DSL programs, Task seeds, and limits.
- [x] Each case compares terminal state, reward, crash status, and program call count exactly, with failures diagnosing the differing observable.
- [x] The tests do not assert or require equivalence of nondeterministic model text.
- [x] Existing V1-wide Ruff formatting findings are neither modified nor made a gate for this ticket.

## Resolution record

The adapter shares the Python 3.11 `uv` runtime with the importable Karel and MiniGrid V1 components. It is deliberately limited to fixed-program evaluation, not model generation or search. Both the adapter and its independent oracle enter through the established V1 replay-runtime boundary. That boundary received a backward-compatible fix so Karel respects the supplied `max_calls` limit (the prior default remains unchanged), which is necessary for identical-limit equivalence. Targeted equivalence tests, adapter type checking, and adapter-test Ruff checks pass. The full repository suite still cannot collect legacy local-LLM tests because the V2 lockfile does not include their LangChain dependency; that pre-existing V1 runtime boundary is not remediated here.
