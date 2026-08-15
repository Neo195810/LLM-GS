from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .evaluator import run_many_doorkey_mvp


AGENTS = [
    {
        "name": "PlannerAgent",
        "role": "decompose a task into reusable subgoals",
        "preference": "prefer reusable subgoals over raw action sequences",
    },
    {
        "name": "SkillManagerAgent",
        "role": "retrieve compatible skills for each subgoal",
        "preference": "prefer high-confidence skills with matching metadata",
    },
    {
        "name": "EvaluatorAgent",
        "role": "execute the policy loop and measure outcomes",
        "preference": "prefer reproducible seed-based evaluation",
    },
    {
        "name": "CriticRepairAgent",
        "role": "analyze evaluator output and choose a repair/store action",
        "preference": "prefer structured repair operators over free-form feedback",
    },
    {
        "name": "SkillMemoryAgent",
        "role": "persist critic-approved successful skills",
        "preference": "persist only critic-approved successful skills",
    },
]


DATA_FLOW = [
    {
        "from": "PlannerAgent",
        "to": "SkillManagerAgent",
        "artifact": "subgoal_template",
    },
    {
        "from": "SkillManagerAgent",
        "to": "EvaluatorAgent",
        "artifact": "retrieved_skill_plan",
    },
    {
        "from": "EvaluatorAgent",
        "to": "CriticRepairAgent",
        "artifact": "execution_result",
    },
    {
        "from": "CriticRepairAgent",
        "to": "SkillMemoryAgent",
        "artifact": "critique",
    },
    {
        "from": "SkillMemoryAgent",
        "to": "SkillManagerAgent",
        "artifact": "learned_skill_records",
    },
]


def run_doorkey_agent_loop(
    seeds: Iterable[int],
    max_steps: int = 200,
    skill_store_path: str | Path | None = None,
    include_runs: bool = False,
) -> dict[str, Any]:
    """Run the DoorKey MVP as an explicit Skill-GS agent workflow."""

    seed_list = list(seeds)
    evaluation = run_many_doorkey_mvp(
        seeds=seed_list,
        max_steps=max_steps,
        skill_store_path=skill_store_path,
    )
    first_run = evaluation["runs"][0] if evaluation["runs"] else None
    run_summary = _compact_run_summary(evaluation)

    result = {
        "task": "DoorKey",
        "seeds": seed_list,
        "agent_sequence": [agent["name"] for agent in AGENTS],
        "agents": [dict(agent) for agent in AGENTS],
        "data_flow": [dict(edge) for edge in DATA_FLOW],
        "planner_agent": _planner_output(first_run),
        "skill_manager_agent": _skill_manager_output(first_run),
        "evaluator_agent": _evaluator_output(run_summary),
        "critic_agent": _critic_output(evaluation),
        "skill_memory": evaluation.get(
            "skill_memory",
            {
                "store_path": str(Path(skill_store_path)) if skill_store_path else None,
                "stored_skills": 0,
                "updated_skills": 0,
                "skipped_skills": 0,
                "skipped_runs": 0,
            },
        ),
        "run_summary": run_summary,
    }
    if include_runs:
        result["runs"] = evaluation["runs"]
    return result


def _compact_run_summary(evaluation: dict[str, Any]) -> dict[str, Any]:
    return {
        "task": evaluation["task"],
        "num_runs": evaluation["num_runs"],
        "successes": evaluation["successes"],
        "success_rate": evaluation["success_rate"],
        "failed_seeds": evaluation["failed_seeds"],
        "average_steps_successful": evaluation["average_steps_successful"],
        "critic_decisions": evaluation["critic_decisions"],
    }


def _planner_output(run: dict[str, Any] | None) -> dict[str, Any]:
    if run is None:
        return {"subgoals": []}
    return {"subgoals": run["plan"]["subgoals"]}


def _skill_manager_output(run: dict[str, Any] | None) -> dict[str, Any]:
    if run is None:
        return {"retrieved_skill_count": 0, "retrieved_skill_names": []}
    skill_names = [
        step["skill_name"]
        for step in run["plan"]["steps"]
        if step.get("skill_name") is not None
    ]
    return {
        "retrieved_skill_count": len(skill_names),
        "retrieved_skill_names": skill_names,
    }


def _evaluator_output(run_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "num_runs": run_summary["num_runs"],
        "success_rate": run_summary["success_rate"],
        "failed_seeds": run_summary["failed_seeds"],
        "average_steps_successful": run_summary["average_steps_successful"],
    }


def _critic_output(evaluation: dict[str, Any]) -> dict[str, Any]:
    return {"critic_decisions": evaluation["critic_decisions"]}
