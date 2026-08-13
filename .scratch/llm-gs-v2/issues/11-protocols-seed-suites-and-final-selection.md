# 11 — Protocols, Seed Suites, and final selection

**What to build:** Make experiments scientifically separable with versioned Seed Suites, read-only Frozen Memory evaluation, sequential isolated Online Memory Lineages, deterministic final-Candidate-Program selection before held-out evaluation, and paired-budget protocol enforcement.

**Blocked by:** 10 — Memory Repair and Memory + Reflect.

**Status:** blocked

**Acceptance criteria:**

- [ ] Seed Suites partition memory-training, development, and held-out seeds; held-out evidence cannot influence search, repair, or Frozen Memory.
- [ ] Frozen Memory cannot mutate during evaluation, while each Online method/algorithm/replicate uses an isolated ordered Memory Lineage.
- [ ] Exactly one final Candidate Program is selected by the specified deterministic lexicographic rule before its one held-out evaluation.
- [ ] Protocol tests demonstrate arm isolation, stable update order, and paired seed/budget handling.
