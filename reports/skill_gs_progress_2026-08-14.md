# Skill-GS Progress Report

Date: 2026-08-14  
Branch: `Branch_NerdyClaush`  
Repo: `F:\GitHub_Experiment\LLM-GS-team`

## Current Status

We have completed the first runnable Skill-GS MVP loop on the repo-native Karel
DoorKey task. This is not yet the full paper-level Skill-GS algorithm, but it
is now more than a module skeleton: the pipeline can plan, execute, evaluate,
and report results.

Implemented components:

- `prog_policies/skill_gs/doorkey_state.py`
  - Extracts DoorKey state from the Karel environment.
  - Tracks agent position, key marker, goal marker, divider wall, and door-open state.

- `prog_policies/skill_gs/doorkey_policy.py`
  - Implements a fixed BFS/rule-based DoorKey policy.
  - Solves the task by navigating to the key marker, picking it up, then navigating to the goal marker and placing a marker.

- `prog_policies/skill_gs/evaluator.py`
  - Runs the DoorKey MVP loop.
  - Records success, reward, step count, termination/crash status, retrieved skill plan, action trace, and Critic/Repair output.

- `prog_policies/skill_gs/skill_memory.py`
  - Persists successful evaluator results as cumulative JSON skill records.
  - Tracks source agent, source task, source subgoal, source seeds, and evaluation count.

- `scripts/skill_gs/run_doorkey_mvp.py`
  - CLI entry point for single-seed and multi-seed smoke runs.

- `tests/test_skill_gs_doorkey_mvp.py`
  - Verifies state extraction, fixed policy behavior, planner skill mapping, seed 0 success, and seeds 0..7 success.

## Verification

Unit test command:

```powershell
python -m unittest tests.test_skill_gs_doorkey_mvp -v
```

Observed result:

```text
Ran 5 tests
OK
```

Multi-seed smoke command:

```powershell
python scripts\skill_gs\run_doorkey_mvp.py --seeds 0 1 2 3 4 5 6 7 --trace-limit 0
```

Observed result:

```json
{
  "task": "DoorKey",
  "num_runs": 8,
  "successes": 8,
  "success_rate": 1.0,
  "failed_seeds": [],
  "average_steps_successful": 15.625,
  "critic_decisions": {
    "store_skill": 8
  }
}
```

## What This Proves

The project environment can run the current DoorKey MVP successfully.

The current Skill-GS layer can already support:

- task decomposition through `HierarchicalPlanner`
- skill retrieval through `SkillManager`
- fixed policy execution through `DoorKeyFixedPolicy`
- evaluator output through `run_doorkey_mvp`
- evaluator-to-critic analysis through `CriticRepairAgent`
- cumulative skill recording through `record_skills_from_evaluation`
- reproducible smoke testing over seeds 0..7

For DoorKey, the planner now retrieves reasonable skills:

- `locate_key`, `navigate_to_key`, `navigate_to_door`, `navigate_to_goal`
  - `navigate_forward_until_blocked`
- `pickup_key`
  - `pick_marker`
- `open_door`
  - `unlock_door_with_key`

In this Karel DoorKey task, opening the door is triggered by picking up the key
marker, so `unlock_door_with_key` uses the same DSL action as `pickMarker` but
has different semantic metadata.

## Current Limitations

The current BFS/rule-based policy is a stable baseline, not the final Skill-GS
algorithm.

The evaluator now produces useful result dictionaries and connects them to
`CriticRepairAgent`. Successful runs produce `repair_operator="store_skill"`;
step-budget failures produce structured repair hints such as
`repair_operator="retrieve_alternative_skill"`.

The skill database can now accumulate successful skills into
`data/skill_gs/doorkey_skills.json` when the CLI is run with `--skill-store`.
The first DoorKey multi-seed run stores 6 learned skills and updates them
across seeds 0..7, producing `num_evaluations=8` on each record.

This MVP uses the repo-native Karel DoorKey task. The paper-related MiniGrid
tasks, such as PutNear, RedBlueDoor, and LavaGap, are still future integration
targets.

## Next-Step Decision

Completed next step: evaluator output is now connected to `CriticRepairAgent`.

Reason:

- The evaluator outputs `success`, `reward`, `trace`, `terminated`, and `crashed`.
- `CriticRepairAgent` accepts evaluator-like dictionaries.
- This creates a complete MVP story:
  - planner retrieves skills
  - policy executes
  - evaluator records outcome
  - critic analyzes success/failure
  - repair signal says whether to store, replace, guard, or retrieve another skill

Verified critic behavior:

- DoorKey success returns `repair_operator="store_skill"`.
- Step-budget failure returns `repair_operator="retrieve_alternative_skill"`.
- Multi-seed summary returns `critic_decisions={"store_skill": 8}`.

Completed next step: the skill database can now be cumulative.

Reason:

- The critic emits `store_skill` on successful runs.
- The evaluator can persist successful plan steps into a JSON skill store.
- The JSON records include metadata for future agent-specific learning:
  `source_agent`, `source_task`, `source_subgoal`, `source_skill_id`, and `source_seeds`.

Verified skill-memory behavior:

- DoorKey seeds 0..7 produce 6 learned skill records.
- Each learned record has `num_evaluations=8`.
- Failed or incomplete evaluations do not write skills.

Suggested next task order:

1. Decide how agent roles should read/write skills.
2. Add a compact report output that summarizes success rate, average steps, critic decisions, and skill-memory updates.
3. Later: integrate this loop with the original LLM-GS candidate search.
