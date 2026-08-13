# 09 — Structured Retrieval provenance

**What to build:** Retrieve compatible Experience Memory deterministically for a failed Candidate Program using explicit Experiment Context, Failure Type/Reason, state-feature, and normalized-AST signals, with complete candidate and reason-code provenance.

**Blocked by:** 08 — Memory Curator and Frozen Memory Snapshot.

**Status:** blocked

**Acceptance criteria:**

- [ ] Incompatible Task, DSL, environment, or model context is hard-filtered before ranking.
- [ ] Deterministic buckets, component values, tie-breaks, category quotas, and selected Memory Entries are persisted as retrieval provenance.
- [ ] Retrieval ordering/configuration is versioned, recorded in the Manifest, calibrated only on development data, and frozen before held-out Snapshot construction.
- [ ] No embedding or semantic-vector retrieval is introduced in this release.
