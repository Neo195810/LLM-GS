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

- `prog_policies/skill_gs/agent_workflow.py`
  - Wraps the DoorKey MVP as an explicit multi-agent data flow.
  - Reports the Planner, Skill Manager, Evaluator, Critic/Repair, and Skill Memory roles without changing the underlying DoorKey solver.

- `scripts/skill_gs/run_doorkey_mvp.py`
  - CLI entry point for single-seed and multi-seed smoke runs.

- `scripts/skill_gs/run_agent_loop.py`
  - CLI entry point for the explicit Skill-GS agent workflow.

- `tests/test_skill_gs_doorkey_mvp.py`
  - Verifies state extraction, fixed policy behavior, planner skill mapping, seed 0 success, seeds 0..7 success, and skill-memory idempotency.

- `tests/test_skill_gs_agent_workflow.py`
  - Verifies the agent sequence, data-flow artifacts, evaluator summary, and skill-memory output.

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

Initial multi-seed smoke command:

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

Extended skill-memory command:

```powershell
python -c "import json; from prog_policies.skill_gs.evaluator import run_many_doorkey_mvp; result = run_many_doorkey_mvp(range(8, 128), skill_store_path=r'data\skill_gs\doorkey_skills.json'); keys = ['task', 'num_runs', 'successes', 'success_rate', 'failed_seeds', 'average_steps_successful', 'critic_decisions', 'skill_memory']; print(json.dumps({key: result[key] for key in keys}, indent=2))"
```

Observed result:

```json
{
  "task": "DoorKey",
  "num_runs": 120,
  "successes": 120,
  "success_rate": 1.0,
  "failed_seeds": [],
  "average_steps_successful": 15.041666666666666,
  "critic_decisions": {
    "store_skill": 120
  },
  "skill_memory": {
    "store_path": "data\\skill_gs\\doorkey_skills.json",
    "stored_skills": 0,
    "updated_skills": 720,
    "skipped_skills": 0,
    "skipped_runs": 0
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
- explicit agent data flow through `run_doorkey_agent_loop`
- reproducible smoke testing over seeds 0..127

Current agent workflow:

```text
PlannerAgent -> SkillManagerAgent -> EvaluatorAgent -> CriticRepairAgent -> SkillMemoryAgent
```

The agent layer is intentionally role-based rather than personality-based:

- PlannerAgent prefers reusable subgoals over raw action sequences.
- SkillManagerAgent prefers high-confidence skills with matching metadata.
- EvaluatorAgent prefers reproducible seed-based evaluation.
- CriticRepairAgent prefers structured repair operators over free-form feedback.
- SkillMemoryAgent persists only critic-approved successful skills.

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
The DoorKey skill-memory run now covers seeds 0..127. It stores 6 learned
skills, and each record has `num_evaluations=128`.

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
- Extended multi-seed summary returns `critic_decisions={"store_skill": 120}` for seeds 8..127.

Completed next step: the skill database can now be cumulative.

Reason:

- The critic emits `store_skill` on successful runs.
- The evaluator can persist successful plan steps into a JSON skill store.
- The JSON records include metadata for future agent-specific learning:
  `source_agent`, `source_task`, `source_subgoal`, `source_skill_id`, and `source_seeds`.

Verified skill-memory behavior:

- DoorKey seeds 0..127 produce 6 learned skill records.
- Each learned record has `num_evaluations=128`.
- Repeated seed observations are skipped instead of double-counted.
- Failed or incomplete evaluations do not write skills.

Suggested next task order:

1. Add a compact report output that summarizes success rate, average steps, critic decisions, and skill-memory updates.
2. Decide whether SkillManagerAgent should rank learned skills by seed coverage, success rate, or task metadata.
3. Later: integrate this loop with the original LLM-GS candidate search.
