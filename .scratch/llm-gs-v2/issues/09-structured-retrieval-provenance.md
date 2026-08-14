# 09 — Structured Retrieval provenance

**What to build:** Retrieve compatible Experience Memory deterministically for a failed Candidate Program using explicit Experiment Context, Failure Type/Reason, state-feature, and normalized-AST signals, with complete candidate and reason-code provenance.

**Blocked by:** 08 — Memory Curator and Frozen Memory Snapshot.

**Status:** done

**Acceptance criteria:**

- [x] Incompatible Task, DSL, environment, or model context is hard-filtered before ranking. Verified: `src/llm_gs/memory.py:177,190` (`task_compatible`, `compatible_entries` filter), `tests/test_memory.py:83,113`.
- [x] Deterministic buckets, component values, tie-breaks, category quotas, and selected Memory Entries are persisted as retrieval provenance. Verified: `src/llm_gs/memory.py:191,200,206` (ranking, tiebreaker, `reason_codes`), `src/llm_gs/contracts.py:175,186` (`RetrievalCandidateComponents`, `RetrievalOutcome`), `src/llm_gs/storage.py:521` (`save_retrieval_outcome`), `tests/test_memory.py:27,51`.
- [x] Retrieval ordering/configuration is versioned, recorded in the Manifest, calibrated only on development data, and frozen before held-out Snapshot construction. Verified: `src/llm_gs/memory.py:15` (`RETRIEVER_VERSION`), `tests/test_offline_tracer_bullet.py:617,644`.
- [x] No embedding or semantic-vector retrieval is introduced in this release. Verified: `grep -i "embedding|vector|semantic" src/llm_gs/memory.py` returns zero matches.
