# 10 — Memory Repair and Memory + Reflect

**What to build:** Complete the four-way post-failure intervention by adding Memory Repair and Memory + Reflect, supplying allowlisted retrieved data to repair/diagnosis while keeping the initial Proposer memory-free and recording Retrieval Outcomes separately from Memory Entries.

**Blocked by:** 09 — Structured Retrieval provenance.

**Status:** blocked

**Acceptance criteria:**

- [ ] Regenerate, Reflect, Memory Repair, and Memory + Reflect share one configurable post-failure intervention point.
- [ ] The initial Proposer receives no Experience Memory in the primary ablation.
- [ ] Memory and evidence are serialized through versioned allowlists with explicit data boundaries, never as historical instructions.
- [ ] Each Retrieval Outcome records subsequent improvement, failure-type change, or success without mutating source entries.
