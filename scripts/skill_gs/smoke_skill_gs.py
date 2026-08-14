from __future__ import annotations

import argparse
import json
import pathlib
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from prog_policies.minigrid.dsl import MinigridDSL
from prog_policies.skill_gs import (
    CriticRepairAgent,
    HierarchicalPlanner,
    JsonSkillStore,
    SkillManager,
    make_default_minigrid_skills,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Skill-GS module smoke run.")
    parser.add_argument("--task", default="PutNear")
    args = parser.parse_args()

    dsl = MinigridDSL()
    store = JsonSkillStore()
    store.extend(make_default_minigrid_skills(dsl))
    manager = SkillManager(store)
    planner = HierarchicalPlanner()
    plan = planner.plan(
        args.task,
        manager,
        context_tags=[
            "object_at_agent",
            "is_carrying_object",
            "door_in_front",
            "lava_in_front",
        ],
    )

    critique = CriticRepairAgent().analyze(
        {
            "task": args.task,
            "success": False,
            "reward": 0.5,
            "trace": ["pickup", "pickup", "pickup", "pickup", "pickup", "pickup"],
            "current_subgoal": "navigate_near_target_object",
            "failed_node_id": 17,
        }
    )

    print(
        json.dumps(
            {
                "task": args.task,
                "skill_count": len(store.all()),
                "plan": plan.to_dict(),
                "critique": critique.to_dict(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
