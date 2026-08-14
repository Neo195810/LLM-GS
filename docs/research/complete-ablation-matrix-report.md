# Complete Frozen ablation matrix — report

Real, retained result of `llm-gs matrix run docs/specs/complete-ablation-matrix.yaml
--workspace artifacts/complete-ablation-matrix-fake-run`, run 2026-08-14 with the
default (fake, deterministic) model client — no live OpenAI calls, no fabricated
numbers. Machine-readable data: `docs/research/complete-ablation-matrix-report.json`.
Backing store: `artifacts/complete-ablation-matrix-fake-run/attempt-store.sqlite3`.

## Coverage

48 of 48 arms completed (4 Tasks x 3 Search Strategies x 4 failure-handling
strategies, paired seeds and fixed budgets from the spec's `seed_suite` and
`max_repair_cycles: 1`). Tasks: CleanHouse, FourCorners, DoorKey, RedBlueDoor.
Search strategies: single_candidate (Hill Climbing baseline), CEM, CEBS.
Failure strategies: regenerate, reflect, memory_repair, memory_reflect.

- `missingness`: 0 incomplete executions, 0 unreported arms.
- `exclusions`: none.
- `failure_classes`: 0 budget / 0 infrastructure / 0 model_output / 0 replacements.

Every preregistered arm resolved to a completed state; no arm was dropped or
substituted.

## Frozen vs Online

The spec (`display_name: complete-frozen-ablation`) defines only the Frozen-Memory
matrix, so this run has 0 Online arms — that is the spec's scope, not missing data.
`matrix_report` keeps Frozen and Online statistics in separate buckets and never
pools them; this report only speaks to the Frozen protocol.

- Frozen: 48/48 arms, fixed_budget_success_rate = 0.0, Wilson-95 CI [0.0, 0.074].
- Online: 0 arms (out of scope for this spec).

The 0.0 success rate is expected and non-fabricated: the fake client returns
scripted proposer/repair responses that are not written to solve any of the four
tasks, so every arm exhausts its fixed budget without success. This run
demonstrates real, deterministic, paired execution and reporting plumbing across
every arm — it is not a claim about live-model performance.

## V1/V2-adapter baseline

`single_candidate` (Hill Climbing) is the pre-existing V1-equivalent baseline
carried through every Task/failure-strategy combination as a system control, not
as an intervention-factor level alongside CEM/CEBS; see
`tests/test_v1_adapter_equivalence.py` for the fixed-program V1/V2 equivalence
checks this baseline depends on.

## Reproduction

```
llm-gs matrix run docs/specs/complete-ablation-matrix.yaml \
  --workspace artifacts/complete-ablation-matrix-fake-run
```

Omit `--enable-live-openai` to keep using the deterministic fake client (as this
report does). Re-running against a fresh empty workspace reproduces identical
`arm_states`/`missingness`/`failure_classes` because the fake client is
deterministic per seed.
