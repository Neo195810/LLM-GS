from __future__ import annotations

from .schemas import SkillPlan, SkillPlanStep, SkillQuery
from .skill_manager import SkillManager


class HierarchicalPlanner:
    """Template planner that maps MiniGrid tasks into reusable subgoals."""

    TASK_TEMPLATES = {
        "PutNear": [
            "locate_source_object",
            "navigate_to_source_object",
            "pickup_source_object",
            "locate_target_object",
            "navigate_near_target_object",
            "drop_source_object",
        ],
        "RedBlueDoor": [
            "locate_red_door",
            "navigate_to_red_door",
            "open_red_door",
            "locate_blue_door",
            "navigate_to_blue_door",
            "open_blue_door",
        ],
        "LavaGap": [
            "avoid_lava",
            "navigate_to_gap",
            "cross_gap",
            "navigate_to_goal",
        ],
        "DoorKey": [
            "locate_key",
            "navigate_to_key",
            "pickup_key",
            "navigate_to_door",
            "open_door",
            "navigate_to_goal",
        ],
    }

    def plan(
        self,
        task: str,
        skill_manager: SkillManager,
        context_tags: list[str] | None = None,
        top_k: int = 1,
    ) -> SkillPlan:
        subgoals = self.TASK_TEMPLATES.get(task, [f"solve_{task.lower()}"])
        context_tags = context_tags or []
        steps: list[SkillPlanStep] = []

        for subgoal in subgoals:
            query = SkillQuery(
                task=task,
                subgoal=subgoal,
                context_tags=[*context_tags, *_tags_for_subgoal(subgoal)],
                top_k=top_k,
            )
            retrieved = skill_manager.retrieve(query)
            if retrieved:
                best = retrieved[0]
                steps.append(
                    SkillPlanStep(
                        subgoal=subgoal,
                        skill_id=best.skill.skill_id,
                        skill_name=best.skill.name,
                        dsl_source=best.skill.dsl_source,
                        reason=", ".join(best.reasons),
                    )
                )
            else:
                steps.append(
                    SkillPlanStep(
                        subgoal=subgoal,
                        skill_id=None,
                        skill_name=None,
                        dsl_source=None,
                        reason="no_compatible_skill_found",
                    )
                )

        return SkillPlan(task=task, subgoals=subgoals, steps=steps)


def _tags_for_subgoal(subgoal: str) -> list[str]:
    tags: list[str] = []
    if "navigate" in subgoal or "locate" in subgoal or "cross" in subgoal:
        tags.extend(["navigation", "move", "explore"])
    if "pickup" in subgoal or "key" in subgoal:
        tags.extend(["pickup", "object", "key"])
    if "door" in subgoal or "open" in subgoal:
        tags.extend(["door", "toggle", "open"])
    if "drop" in subgoal or "put" in subgoal:
        tags.extend(["drop", "putnear", "object"])
    if "lava" in subgoal:
        tags.extend(["lava", "avoid"])
    return tags
