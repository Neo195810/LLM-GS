# 08 — Memory Curator and Frozen Memory Snapshot

**What to build:** Derive a versioned, rebuildable Experience Memory view from immutable Attempt Store facts through a deterministic Memory Curator, including exact duplicate treatment, selective retention, balanced Frozen Memory construction, and source Search Strategy provenance.

**Blocked by:** 07 — Append-only Attempt Store and recovery.

**Status:** blocked

**Acceptance criteria:**

- [ ] Memory Entries are derived from rather than substituted for Program Attempts, and rebuilding them never mutates historical facts.
- [ ] Exact duplicate merging requires the specified compatibility, failure, normalized-AST, and state-feature keys; approximate matches remain separate.
- [ ] Frozen Snapshot construction applies preregistered balanced quotas and preserves source-frequency/Search Strategy provenance.
- [ ] Curation is deterministic and tested for append-only and duplicate invariants.
