# 12 — Recovery, reporting, and self-verifying export

**What to build:** Complete the local research workflow with resume, memory build, held-out evaluation, attempt inspection, deterministic reports, and conflict-safe export/import bundles that expose all completed and failed activity.

**Blocked by:** 11 — Protocols, Seed Suites, and final selection.

**Status:** blocked

**Acceptance criteria:**

- [ ] The CLI provides run, resume, memory build, evaluate, report, inspect attempt, and validate through resolved manifests and safety validation.
- [ ] Reports separate Frozen/Online results and show success under fixed budget, costs, repair/retrieval impact, outcome distributions, missingness, Infrastructure Failures, and Model Output Failures.
- [ ] Exports include scoped facts, Manifest, Memory Snapshot, Artifact hashes, and checksums; import validates schemas and identity and rejects conflicts.
- [ ] Infrastructure retries, replacement executions, and incomplete work remain visible rather than silently excluded.
