# 10 — Memory Repair and Memory + Reflect

**What to build:** Complete the four-way post-failure intervention by adding Memory Repair and Memory + Reflect, supplying allowlisted retrieved data to repair/diagnosis while keeping the initial Proposer memory-free and recording Retrieval Outcomes separately from Memory Entries.

**Blocked by:** 09 — Structured Retrieval provenance.

**Status:** done

**Acceptance criteria:**

- [x] Regenerate, Reflect, Memory Repair, and Memory + Reflect share one configurable post-failure intervention point. Verified: `src/llm_gs/contracts.py:40` (`FailureStrategySpecification`), `src/llm_gs/execution.py:235,337,349,369` (single dispatch on `failure_strategy`), `tests/test_offline_tracer_bullet.py:278`.
- [x] The initial Proposer receives no Experience Memory in the primary ablation. Verified: `src/llm_gs/execution.py:249` (memory-free initial candidate).
- [x] Memory and evidence are serialized through versioned allowlists with explicit data boundaries, never as historical instructions. Verified: `src/llm_gs/memory.py:383` (`serialize_repair_context`), `src/llm_gs/memory.py:442,455` (data boundary marker, allowlisted fields), `tests/test_memory.py:40`.
- [x] Each Retrieval Outcome records subsequent improvement, failure-type change, or success without mutating source entries. Verified: `src/llm_gs/storage.py:531,561` (`record_retrieval_impact`, `record_no_retrieval_impact`), `src/llm_gs/contracts.py:193` (`subsequent_*` fields), `tests/test_offline_tracer_bullet.py:498,538-540,549`.
