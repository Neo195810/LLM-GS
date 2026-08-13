# 02 — V1 adapter deterministic equivalence

**What to build:** Make the V1 baseline trustworthy through V2 adapters by proving that a fixed DSL program, identical Task seeds, and identical execution limits yield the same terminal state, reward, crash status, and program call count in V1 and the adapter. Model-generated text is intentionally outside this comparison.

**Blocked by:** 01 — V2 offline tracer bullet (completed).

**Status:** ready-for-agent

**Acceptance criteria:**

- [ ] Deterministic equivalence cases cover the initial Karel and MiniGrid adapter surfaces with fixed DSL programs, Task seeds, and limits.
- [ ] Each case compares terminal state, reward, crash status, and program call count exactly, with failures diagnosing the differing observable.
- [ ] The tests do not assert or require equivalence of nondeterministic model text.
- [ ] Existing V1-wide Ruff formatting findings are neither modified nor made a gate for this ticket.
