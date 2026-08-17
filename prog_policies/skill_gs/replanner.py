from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .failure_detector import FailureDiagnosis


@dataclass
class RepairPlan:
    status: str
    strategy_id: str
    next_attempt: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    perturbation: dict[str, Any] = field(default_factory=dict)
    selected_skill: dict[str, Any] = field(default_factory=dict)
    plan_variant: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def replan_after_failure(
    diagnosis: FailureDiagnosis,
    attempt: int,
    current_max_steps: int,
    retry_max_steps: int,
    perturbation: dict[str, Any] | None = None,
    skill_ranking: dict[str, Any] | None = None,
    can_retry: bool = True,
) -> RepairPlan:
    """Convert a failure diagnosis into the next retry configuration."""

    if diagnosis.success:
        return RepairPlan(
            status="stop",
            strategy_id="store_skill",
            rationale="Evaluation succeeded; store the successful skill trace.",
            perturbation=perturbation or {},
        )

    if not can_retry:
        return RepairPlan(
            status="stop",
            strategy_id="max_attempts_exhausted",
            rationale="No retry budget remains for this seed.",
            perturbation=perturbation or {},
        )

    strategy_id = (
        perturbation.get("strategy_id")
        if perturbation
        else diagnosis.recommended_repair
    )
    selected_skill = _select_skill(skill_ranking)
    plan_variant = _make_plan_variant(diagnosis, skill_ranking, selected_skill)
    next_max_steps = _next_max_steps(strategy_id, current_max_steps, retry_max_steps)
    next_attempt = {
        "attempt": attempt + 1,
        "max_steps": next_max_steps,
        "reason": diagnosis.failure_type,
    }
    if selected_skill:
        next_attempt["selected_skill_id"] = selected_skill["skill_id"]
        next_attempt["selected_skill_name"] = selected_skill.get("name")

    return RepairPlan(
        status="retry",
        strategy_id=strategy_id,
        next_attempt=next_attempt,
        rationale=_rationale(diagnosis.failure_type, strategy_id),
        perturbation=perturbation or {},
        selected_skill=selected_skill,
        plan_variant=plan_variant,
    )


def _next_max_steps(
    strategy_id: str,
    current_max_steps: int,
    retry_max_steps: int,
) -> int:
    if strategy_id in {
        "increase_step_budget",
        "retrieve_alternative_skill",
        "insert_progress_guard",
        "insert_missing_subgoal",
        "replace_subtree",
    }:
        return max(current_max_steps, retry_max_steps)
    return current_max_steps


def _rationale(failure_type: str, strategy_id: str) -> str:
    return (
        f"Diagnosis {failure_type} selected repair strategy {strategy_id}; "
        "rerun with the planned retry configuration."
    )


def _select_skill(skill_ranking: dict[str, Any] | None) -> dict[str, Any]:
    if not skill_ranking:
        return {}
    ranked = skill_ranking.get("ranked_skills", [])
    if not ranked:
        return {}
    top = ranked[0]
    return {
        "skill_id": top["skill_id"],
        "name": top.get("name"),
        "score_after": top.get("score_after"),
        "ranking_reasons": list(top.get("reasons", [])),
    }


def _make_plan_variant(
    diagnosis: FailureDiagnosis,
    skill_ranking: dict[str, Any] | None,
    selected_skill: dict[str, Any],
) -> dict[str, Any]:
    if not skill_ranking or not selected_skill:
        return {}
    query = skill_ranking.get("query", {})
    return {
        "source": "skill_ranking",
        "failure_type": diagnosis.failure_type,
        "ranking_policy": skill_ranking.get("ranking_policy"),
        "target_subgoal": query.get("subgoal"),
        "context_tags": list(query.get("context_tags", [])),
        "selected_skill_id": selected_skill["skill_id"],
        "selected_skill_name": selected_skill.get("name"),
    }
