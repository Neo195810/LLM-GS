# Skill-GS Adaptive Core Progress and Experiment Report

Date: 2026-08-15  
Branch: `Branch_NerdyClaush`  
Repo: `F:\GitHub_Experiment\LLM-GS-team`

## Summary

Today we moved the DoorKey MVP from a stable BFS/rule-based baseline into a
small but complete Adaptive Core loop.

The current system can:

- run the repo-native Karel DoorKey task over fixed seed ranges
- detect failure from evaluator and critic output
- select a seeded repair perturbation
- replan the next attempt
- retry failed seeds
- persist attempt-level adaptive memory
- summarize success rate, retry count, replan count, and failure types

This is still not the full paper-level Skill-GS algorithm. The current version
uses the BFS/rule-based DoorKey policy as a stable baseline and tests Adaptive
Core behavior by controlling the step budget.

## Implemented Components

The Skill-GS layer now includes the following Adaptive Core modules:

| Component | File | Role |
|---|---|---|
| Failure Detector | `prog_policies/skill_gs/failure_detector.py` | Converts evaluator and critic output into a stable failure diagnosis |
| Stochastic Perturbation | `prog_policies/skill_gs/stochastic_perturbation.py` | Selects a repair strategy with a reproducible random seed |
| Replanner | `prog_policies/skill_gs/replanner.py` | Converts a diagnosis and perturbation into the next attempt configuration |
| Adaptive Memory | `prog_policies/skill_gs/adaptive_memory.py` | Stores attempts, diagnoses, repair plans, and repair outcomes |
| Retry Wrapper | `prog_policies/skill_gs/adaptive_retry.py` | Connects detector, perturbation, replanning, retry, and memory |
| Agent Workflow | `prog_policies/skill_gs/agent_workflow.py` | Exposes the DoorKey loop as a role-based agent data flow |

The current data flow is:

```text
Evaluator output
-> Failure Detector
-> Seeded Perturbation
-> Replanner
-> Retry Wrapper
-> Adaptive Memory
```

At the agent level, the data flow is:

```text
PlannerAgent
-> SkillManagerAgent
-> EvaluatorAgent
-> CriticRepairAgent
-> SkillMemoryAgent
```

## Experiment Setup

All experiments used:

- task: Karel DoorKey
- policy: current BFS/rule-based fixed policy
- adaptive mode: enabled
- max attempts: 2
- perturbation seed: 123
- output directory: `output/skill_gs/`

The failure is intentionally induced through step-budget limits. This means the
experiment is not trying to make BFS behave badly. Instead, it tests whether the
Adaptive Core can detect that the first attempt ran out of budget, generate a
repair plan, retry, and record the outcome.

Example command:

```powershell
python scripts\skill_gs\run_agent_loop.py --seeds 0 --adaptive-retry --initial-max-steps 10 --retry-max-steps 22 --max-attempts 2 --perturbation-seed 123
```

## Experiment 1: Seeds 0..127, Broad Retry Budget

Configuration:

```text
seeds = 0..127
initial max_steps = 10
retry max_steps = 100
max_attempts = 2
```

Result:

| Metric | Value |
|---|---:|
| total seeds | 128 |
| total attempts | 242 |
| first-attempt successes | 14 |
| retried seeds | 114 |
| replan count | 114 |
| retry successes | 114 |
| retry failures | 0 |
| final successes | 128 |
| final success rate | 1.0 |
| average successful steps | 15.078125 |

Interpretation:

With `initial max_steps=10`, most seeds cannot finish on the first attempt.
However, a broad retry budget of 100 solves every failed seed. This verifies the
end-to-end Adaptive Core pipeline under a generous repair budget.

Result file:

```text
output/skill_gs/adaptive_retry_seed0_127_max10_retry100.json
```

## Experiment 2: Seeds 0..63, Short Budget Tests

| Initial max_steps | Retry max_steps | First success | Retried | Replans | Retry success | Final success | Success rate |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 6 | 50 | 0/64 | 64 | 64 | 64 | 64/64 | 1.0 |
| 8 | 10 | 2/64 | 62 | 62 | 4 | 6/64 | 0.09375 |

Interpretation:

`max_steps=6` is too low for all seeds in 0..63; none of them finish on the
first attempt. When retry budget is raised to 50, every case is repaired.

`max_steps=8` starts to solve a few short-path cases. Only seeds `6` and `16`
succeed immediately. With `retry_max_steps=10`, only four additional seeds are
recovered: `13`, `17`, `25`, and `61`. This shows that a retry budget of 10 is
still too tight for most DoorKey layouts.

Result files:

```text
output/skill_gs/adaptive_retry_seed0_63_max6_retry50.json
output/skill_gs/adaptive_retry_seed0_63_max8_retry10.json
```

## Experiment 3: Retry Budget Sweep, Seeds 0..63

Configuration:

```text
seeds = 0..63
initial max_steps = 10
retry max_steps = 20..30
max_attempts = 2
```

Result:

| retry max_steps | first success | retried | replans | retry success | final success | failed seeds |
|---:|---:|---:|---:|---:|---:|---|
| 20 | 6/64 | 58 | 58 | 54 | 60/64 | 1, 19, 29, 57 |
| 21 | 6/64 | 58 | 58 | 55 | 61/64 | 1, 19, 29 |
| 22 | 6/64 | 58 | 58 | 58 | 64/64 | none |
| 23 | 6/64 | 58 | 58 | 58 | 64/64 | none |
| 24 | 6/64 | 58 | 58 | 58 | 64/64 | none |
| 25 | 6/64 | 58 | 58 | 58 | 64/64 | none |
| 26 | 6/64 | 58 | 58 | 58 | 64/64 | none |
| 27 | 6/64 | 58 | 58 | 58 | 64/64 | none |
| 28 | 6/64 | 58 | 58 | 58 | 64/64 | none |
| 29 | 6/64 | 58 | 58 | 58 | 64/64 | none |
| 30 | 6/64 | 58 | 58 | 58 | 64/64 | none |

Interpretation:

For seeds 0..63, when the first attempt is limited to `max_steps=10`, only 6
seeds succeed immediately. The remaining 58 seeds trigger failure detection and
replanning.

The observed full-success retry threshold is:

```text
retry_max_steps = 22
```

At retry budget 20, four seeds still fail: `1`, `19`, `29`, `57`.
At retry budget 21, three seeds still fail: `1`, `19`, `29`.
At retry budget 22 and above, every seed in 0..63 succeeds.

Result files:

```text
output/skill_gs/adaptive_retry_sweep_seed0_63_max10_retry20_30_summary.json
output/skill_gs/adaptive_retry_sweep_seed0_63_max10_retry20_30_full.json
```

## Failure Detector Observations

The raw critic and formal failure detector do not always produce the same label.
This is expected and useful.

Example from the retry sweep:

```text
raw critic:
  insert_missing_subgoal or retrieve_alternative_skill

formal failure detector:
  step_budget_exhausted
```

The critic looks at task progress and repair hints. The failure detector adds
runtime context, especially whether `steps == max_steps` and the environment did
not terminate. This makes `step_budget_exhausted` the more appropriate diagnosis
for loop engineering experiments.

## Main Findings

1. The BFS/rule-based DoorKey baseline is stable when the step budget is high
   enough.
2. Small step budgets expose controlled failures without changing the task or
   policy.
3. The Adaptive Core successfully turns these failures into retry/replan events.
4. For seeds 0..63, `max_steps=6` is below the observed first-attempt success
   threshold.
5. For seeds 0..63 with `initial max_steps=10`, the observed retry budget needed
   for full success is 22.
6. Retry and replan counts are equal in these experiments because each failed
   seed gets exactly one replan before the second attempt.

## Current Limitations

- The current policy is still a BFS/rule-based baseline, not a learned or LLM
  generated policy.
- Stochastic perturbation currently selects among repair strategies, but it does
  not yet mutate skill ranking or AST structure.
- Replanning currently changes attempt configuration, mainly the step budget.
  It does not yet synthesize a new DSL program.
- Adaptive memory records attempts and repair outcomes, but it does not yet feed
  back into future skill retrieval.

## Suggested Next Steps

1. Add a small report generator that converts `output/skill_gs/*.json` into
   Markdown tables automatically.
2. Add a skill-ranking experiment where learned skills are ranked by seed
   coverage, success rate, or failure signature.
3. Extend replanning beyond step budget repair, such as switching to an
   alternative navigation skill.
4. Later, connect Adaptive Core to original LLM-GS candidate programs so that
   failure detection and repair apply to generated programs, not only the BFS
   baseline.

## Verification

Fresh verification command used after implementing Adaptive Core:

```powershell
python -m unittest tests.test_skill_gs_doorkey_mvp tests.test_skill_gs_agent_workflow tests.test_skill_gs_adaptive_core -v
```

Observed result:

```text
Ran 16 tests
OK
```

The experiment output files are under `output/skill_gs/`, and `output/` is
ignored by `.gitignore`.
