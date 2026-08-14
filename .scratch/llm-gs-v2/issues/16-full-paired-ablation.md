# 16 — Full paired ablation matrix

**What to build:** Execute and report the preregistered comparison of Hill Climbing, CEM, and CEBS across the initial Task suite and four failure-handling strategies, using paired seeds, fixed budgets, shared balanced Frozen Memory where applicable, and separately identified Online arms.

**Blocked by:** 15 — CEBS Search Strategy.

**Status:** done

**Acceptance criteria:**

- [x] Every initial Task/search/failure-strategy arm resolves to one visible Experiment Manifest before held-out work begins. Verified: `build_matrix_manifests` produces 48 manifests (4 Task x 3 search x 4 failure strategy), each registered via `register_matrix_arm` before execution.
- [x] Formal comparisons use paired task/search seeds, frozen replicate and confidence-interval rules, and fixed Evaluation/Model Budgets. Verified: `docs/specs/complete-ablation-matrix.yaml` (`seed_suite`, `search_seed`, `replicates`), Wilson-95 CI in `matrix_report`.
- [x] Reports retain every preregistered outcome and make missingness, exclusions, replacement executions, and failure classes explicit. Verified: `docs/research/complete-ablation-matrix-report.json`/`.md` — 48/48 completed, 0 missingness, 0 exclusions, failure_classes all 0.
- [x] Frozen and Online conclusions remain separate, and V1/V2-adapter controls remain system baselines rather than intervention-factor levels. Verified: `matrix_report` keeps `protocols.Frozen`/`protocols.Online` in separate buckets, never pooled; `single_candidate` (Hill Climbing/V1-equivalent baseline) is a shared control across every Task x failure-strategy cell, not an added intervention level.

**Note:** run used the deterministic fake model client (no live OpenAI calls), per explicit choice — see `docs/research/complete-ablation-matrix-report.md`. Fixed_budget_success_rate is 0.0 across all 48 Frozen arms as an expected consequence of the fake client's scripted (non-task-solving) responses, not a claim about live-model performance.
