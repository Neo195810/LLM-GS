# 12 — Recovery, reporting, and self-verifying export

**What to build:** Complete the local research workflow with resume, memory build, held-out evaluation, attempt inspection, deterministic reports, and conflict-safe export/import bundles that expose all completed and failed activity.

**Blocked by:** 11 — Protocols, Seed Suites, and final selection.

**Status:** done

**Acceptance criteria:**

- [x] The CLI provides run, resume, memory build, evaluate, report, inspect attempt, and validate through resolved manifests and safety validation. Verified: `src/llm_gs/cli.py:272,276,284,291,326,331,340,345,351` (`validate`, `run`, `resume`, `report`, `memory build`, `evaluate`, `inspect attempt`, `export`, `import`).
- [x] Reports separate Frozen/Online results and show success under fixed budget, costs, repair/retrieval impact, outcome distributions, missingness, Infrastructure Failures, and Model Output Failures. Verified: `src/llm_gs/storage.py:707-714` (protocol split, success rate, costs, outcomes, missingness, failure_classes), `src/llm_gs/matrix.py:67`, `tests/test_offline_tracer_bullet.py:644`.
- [x] Exports include scoped facts, Manifest, Memory Snapshot, Artifact hashes, and checksums; import validates schemas and identity and rejects conflicts. Verified: `src/llm_gs/storage.py:786,797,820,831` (export), `src/llm_gs/storage.py:845,847,859,884` (`import_bundle` schema/identity/conflict checks), `tests/test_offline_tracer_bullet.py:121`.
- [x] Infrastructure retries, replacement executions, and incomplete work remain visible rather than silently excluded. Verified: `src/llm_gs/cli.py:157,170` (retry loop, `replacement_execution`), `src/llm_gs/storage.py:712,805` (`incomplete_executions`, `execution_replacements`), `tests/test_offline_tracer_bullet.py:167`, `tests/test_matrix.py:97`.
