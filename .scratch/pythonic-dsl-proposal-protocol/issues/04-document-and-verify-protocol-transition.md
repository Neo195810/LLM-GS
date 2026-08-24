# 04 — Document and verify the protocol transition

**What to build:** The durable domain and architectural decision explain why new Karel/MiniGrid
executions use Pythonic-DSL, while automated regression coverage proves the new protocol does not
alter historical direct-DSL evidence or unrelated tasks.

**Blocked by:** 01 — Add Pythonic proposal admission; 02 — Admit conservative DSL backups; 03 — Report proposal admission paths safely.

**Status:** completed

- [x] The glossary defines the new proposal and admission vocabulary without implementation detail.
- [x] A new ADR records the deterministic Python-first lowering, conservative fallback boundary, and historical compatibility rationale.
- [x] Full automated verification covers proposer, execution, storage, reporting, matrix aggregation, and Karel/MiniGrid compatibility.
- [x] No live run or new direct-versus-Pythonic ablation is introduced.
