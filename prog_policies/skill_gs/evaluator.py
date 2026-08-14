from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from prog_policies.karel import KarelDSL
from prog_policies.karel_tasks import DoorKey

from .doorkey_policy import DoorKeyFixedPolicy
from .doorkey_state import extract_doorkey_state
from .planner import HierarchicalPlanner
from .skill_manager import (
    JsonSkillStore,
    SkillManager,
    make_default_karel_doorkey_skills,
)


KAREL_DOORKEY_ENV_ARGS = {
    "env_height": 8,
    "env_width": 8,
    "crashable": False,
    "leaps_behaviour": True,
    "max_calls": 10000,
}


def run_doorkey_mvp(seed: int = 0, max_steps: int = 200) -> dict[str, Any]:
    task = DoorKey(dict(KAREL_DOORKEY_ENV_ARGS), seed)
    env = task.get_environment()
    policy = DoorKeyFixedPolicy.from_environment(env)
    plan = _build_skill_plan()

    trace = []
    total_reward = 0.0
    terminated = False

    for step_index in range(max_steps):
        action = policy.next_action(env)
        if action is None:
            break

        before = extract_doorkey_state(env)
        env.run_action(action)
        terminated, instant_reward = task.get_reward(env)
        total_reward += instant_reward
        after = extract_doorkey_state(env)
        trace.append(
            {
                "step": step_index + 1,
                "action": action,
                "instant_reward": instant_reward,
                "total_reward": total_reward,
                "agent_before": before.agent,
                "agent_after": after.agent,
                "door_open": after.door_open,
            }
        )

        if terminated or env.is_crashed():
            break

    return {
        "task": "DoorKey",
        "seed": seed,
        "success": bool(terminated and not env.is_crashed() and total_reward >= 1.0),
        "reward": total_reward,
        "steps": len(trace),
        "terminated": terminated,
        "crashed": env.is_crashed(),
        "plan": plan.to_dict(),
        "trace": trace,
    }


def run_many_doorkey_mvp(
    seeds: Iterable[int], max_steps: int = 200
) -> dict[str, Any]:
    runs = [run_doorkey_mvp(seed=seed, max_steps=max_steps) for seed in seeds]
    successes = [run for run in runs if run["success"]]
    failed_seeds = [run["seed"] for run in runs if not run["success"]]
    success_steps = [run["steps"] for run in successes]

    return {
        "task": "DoorKey",
        "num_runs": len(runs),
        "successes": len(successes),
        "success_rate": len(successes) / len(runs) if runs else 0.0,
        "failed_seeds": failed_seeds,
        "average_steps_successful": (
            sum(success_steps) / len(success_steps) if success_steps else None
        ),
        "runs": runs,
    }


def _build_skill_plan():
    dsl = KarelDSL()
    store = JsonSkillStore()
    store.extend(make_default_karel_doorkey_skills(dsl))
    manager = SkillManager(store)
    return HierarchicalPlanner().plan(
        "DoorKey",
        manager,
        context_tags=["karel"],
    )
