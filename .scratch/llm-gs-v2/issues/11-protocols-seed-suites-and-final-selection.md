# 11 — Protocols, Seed Suites, and final selection

**What to build:** Make experiments scientifically separable with versioned Seed Suites, read-only Frozen Memory evaluation, sequential isolated Online Memory Lineages, deterministic final-Candidate-Program selection before held-out evaluation, and paired-budget protocol enforcement.

**Blocked by:** 10 — Memory Repair and Memory + Reflect.

**Status:** done

**Acceptance criteria:**

- [x] Seed Suites partition memory-training, development, and held-out seeds; held-out evidence cannot influence search, repair, or Frozen Memory. Verified: `src/llm_gs/contracts.py:24,31` (`SeedSuiteSpecification`, `partitions_are_disjoint`), `src/llm_gs/execution.py:475` (`_seed_suite`), `tests/test_offline_tracer_bullet.py:884`.
- [x] Frozen Memory cannot mutate during evaluation, while each Online method/algorithm/replicate uses an isolated ordered Memory Lineage. Verified: `src/llm_gs/storage.py:338` (`freeze_memory_snapshot`), `src/llm_gs/execution.py:285,548,552` (`_execute_frozen_memory_protocol`, `fork_memory_lineage`), `tests/test_memory.py:153`.
- [x] Exactly one final Candidate Program is selected by the specified deterministic lexicographic rule before its one held-out evaluation. Verified: `src/llm_gs/execution.py:417,447` (`_select_final_candidate`, `selected_before_held_out`), `src/llm_gs/manifest.py:45` (`FINAL_CANDIDATE_SELECTION_RULE`).
- [x] Protocol tests demonstrate arm isolation, stable update order, and paired seed/budget handling. Verified: `tests/test_offline_tracer_bullet.py:644,884,907`, `tests/test_memory.py:153,195`, `tests/test_matrix.py:25`.
