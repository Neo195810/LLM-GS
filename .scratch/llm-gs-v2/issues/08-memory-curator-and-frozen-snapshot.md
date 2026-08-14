# 08 — Memory Curator and Frozen Memory Snapshot

**What to build:** Derive a versioned, rebuildable Experience Memory view from immutable Attempt Store facts through a deterministic Memory Curator, including exact duplicate treatment, selective retention, balanced Frozen Memory construction, and source Search Strategy provenance.

**Blocked by:** 07 — Append-only Attempt Store and recovery.

**Status:** done

**Acceptance criteria:**

- [x] Memory Entries are derived from rather than substituted for Program Attempts, and rebuilding them never mutates historical facts. Verified: `src/llm_gs/memory.py:32-126` (per-task `curate_*_attempt`), `src/llm_gs/storage.py:327` (`save_memory_entry`, dedup insert-or-ignore), `tests/test_memory.py:27`.
- [x] Exact duplicate merging requires the specified compatibility, failure, normalized-AST, and state-feature keys; approximate matches remain separate. Verified: `src/llm_gs/memory.py:43` (entry_id hash), `tests/test_memory.py:27`.
- [x] Frozen Snapshot construction applies preregistered balanced quotas and preserves source-frequency/Search Strategy provenance. Verified: `src/llm_gs/storage.py:338` (`freeze_memory_snapshot`), `src/llm_gs/storage.py:353` (snapshot_id hash), `tests/test_memory.py:138`.
- [x] Curation is deterministic and tested for append-only and duplicate invariants. Verified: `src/llm_gs/storage.py:473` (`append_memory_lineage_entries`), `tests/test_memory.py:51,153`.
