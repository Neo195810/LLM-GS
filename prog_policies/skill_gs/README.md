# Skill-GS module skeleton

Skill-GS is a thin experimental layer on top of LLM-GS. The current skeleton
keeps the original LLM-GS search loop untouched and adds modular components
that can be wired into experiments later.

## Components

- `skill_manager.py`: JSON-backed skill database plus symbolic retrieval/ranking.
- `planner.py`: task-to-subgoal templates and retrieval-driven plan assembly.
- `critic.py`: evaluator-output to structured repair signal conversion.
- `ast_utils.py`: DSL source to JSON-friendly AST serialization helpers.
- `doorkey_state.py`: Karel DoorKey state extraction for key, goal, agent, and door.
- `doorkey_policy.py`: fixed BFS/rule-based policy for the DoorKey MVP loop.
- `evaluator.py`: DoorKey MVP runner and multi-seed summary.
- `skill_memory.py`: cumulative JSON skill recording from successful evaluator results.
- `baseline_comparison.py`: fair local proxy comparison across one-shot,
  candidate-search, and adaptive Skill-GS groups.
- `evidence_pack.py`: SVG chart and Markdown demo report generation from
  baseline comparison JSON.
- `schemas.py`: shared dataclasses for skill records, queries, plans, and critiques.

## First smoke command

```bash
python scripts/skill_gs/smoke_skill_gs.py --task PutNear
```

Expected behavior: the script seeds a few MiniGrid skills, retrieves skills for
task subgoals, and prints a structured plan plus a critic repair signal.

## DoorKey MVP loop

```bash
python scripts/skill_gs/run_doorkey_mvp.py --seed 0
python scripts/skill_gs/run_doorkey_mvp.py --seeds 0 1 2 3 4 5 6 7
python scripts/skill_gs/run_doorkey_mvp.py --seeds 0 1 2 3 4 5 6 7 --skill-store data/skill_gs/doorkey_skills.json
```

Expected behavior: the script uses the existing Karel DoorKey environment,
wires Skill Manager and Planner into a fixed BFS/rule-based policy, and prints
success, reward, steps, the retrieved skill plan, action traces, and a
Critic/Repair decision. Multi-seed runs also include a `critic_decisions`
summary. With `--skill-store`, successful runs persist learned skills into a
cumulative JSON store with source-agent and source-seed metadata. This is a
smoke baseline for the Skill-GS pipeline, not the final Skill-GS search method.

## Baseline comparison and demo evidence

Run the current fair comparison:

```bash
python scripts/skill_gs/run_baseline_comparison.py --seed-start 0 --seed-end 127 --initial-max-steps 10 --search-candidate-max-steps 10 20 22 24 --ours-retry-budget-schedule 20 22 24 --ours-max-attempts 4 --perturbation-seed 123 --output output/skill_gs/baseline_comparison_seed0_127.json
```

Generate tracked SVG charts and a Markdown demo report:

```bash
python scripts/skill_gs/generate_evidence_pack.py --baseline-json output/skill_gs/baseline_comparison_seed0_127.json
```

The demo evidence pack compares:

```text
LLM-generated one-shot proxy
vs LLM-GS-style candidate search proxy
vs ours Adaptive Skill-GS
```

It is a reproducible local proxy benchmark. It does not call an external LLM API.

## Intended next wiring

1. Feed successful LLM-GS programs/subtrees into `SkillRecord`.
2. Replace the default in-memory skills with a persistent JSON or SQLite store.
3. Attach `HierarchicalPlanner` before candidate generation.
4. Attach `CriticRepairAgent` after evaluation traces are available.
5. Compare LLM-GS, LLM-GS plus retrieval, and full Skill-GS under the same seeds.
