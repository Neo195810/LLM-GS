from __future__ import annotations

from typing import Any

from prog_policies.karel import KarelDSL

from .failure_detector import FailureDiagnosis
from .schemas import RetrievedSkill, SkillQuery
from .skill_manager import (
    JsonSkillStore,
    SkillManager,
    make_default_karel_doorkey_skills,
)


def rank_skills_for_failure(
    candidates: list[RetrievedSkill],
    diagnosis: FailureDiagnosis | dict[str, Any],
    perturbation: dict[str, Any] | None = None,
    top_k: int | None = None,
) -> dict[str, Any]:
    """Rerank retrieved skills using Adaptive Core failure context."""

    failure_type = _diagnosis_value(diagnosis, "failure_type")
    policy = _policy_for_failure(failure_type)
    ranked = [
        _rank_candidate(candidate, failure_type, policy)
        for candidate in candidates
    ]
    ranked.sort(
        key=lambda item: (-item["score_after"], item["skill_id"])
    )
    if top_k is not None:
        ranked = ranked[:top_k]
    return {
        "failure_type": failure_type,
        "ranking_policy": policy,
        "perturbation_strategy": (
            perturbation or {}
        ).get("strategy_id"),
        "ranked_skills": ranked,
    }


def build_default_doorkey_skill_ranking(
    diagnosis: FailureDiagnosis,
    perturbation: dict[str, Any] | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    """Build a DoorKey skill ranking artifact for the adaptive retry trace."""

    dsl = KarelDSL()
    store = JsonSkillStore()
    store.extend(make_default_karel_doorkey_skills(dsl))
    manager = SkillManager(store)
    query = SkillQuery(
        task="DoorKey",
        subgoal=_subgoal_for_failure(diagnosis.failure_type),
        context_tags=_context_tags_for_failure(diagnosis.failure_type),
        top_k=top_k,
    )
    candidates = manager.retrieve(query)
    ranking = rank_skills_for_failure(
        candidates,
        diagnosis,
        perturbation=perturbation,
        top_k=top_k,
    )
    ranking["query"] = {
        "task": query.task,
        "subgoal": query.subgoal,
        "context_tags": query.context_tags,
        "top_k": query.top_k,
    }
    return ranking


def _rank_candidate(
    candidate: RetrievedSkill,
    failure_type: str,
    policy: str,
) -> dict[str, Any]:
    skill = candidate.skill
    score = float(candidate.score)
    reasons = list(candidate.reasons)

    if policy == "prefer_low_complexity_high_success":
        score += skill.success_rate * 2.0
        reasons.append(f"success_rate_bonus={skill.success_rate:.2f}")
        score += min(skill.num_evaluations, 20) * 0.03
        if _has_progress_postcondition(skill.postconditions):
            score += 3.0
            reasons.append("progress_postcondition_bonus")
        if _is_turn_only_skill(skill.semantic_tags, skill.postconditions):
            score -= 3.0
            reasons.append("turn_only_penalty")
        if skill.complexity <= 3:
            score += 2.0
            reasons.append("low_complexity_bonus")
        else:
            penalty = min(skill.complexity, 20) * 0.08
            score -= penalty
            reasons.append(f"complexity_penalty={penalty:.2f}")
    elif policy == "avoid_repeated_failure_signature":
        score += skill.success_rate
        reasons.append(f"success_rate_bonus={skill.success_rate:.2f}")
    elif policy == "prefer_missing_subgoal_completion":
        score += len(set(skill.postconditions)) * 0.3
        reasons.append("postcondition_coverage_bonus")
    else:
        score += skill.success_rate * 0.5
        reasons.append(f"general_success_bonus={skill.success_rate:.2f}")

    if failure_type in skill.failure_signatures:
        score -= 3.0
        reasons.append("known_failure_signature_penalty")

    return {
        "skill_id": skill.skill_id,
        "name": skill.name,
        "score_before": candidate.score,
        "score_after": round(score, 6),
        "complexity": skill.complexity,
        "success_rate": skill.success_rate,
        "num_evaluations": skill.num_evaluations,
        "failure_signatures": list(skill.failure_signatures),
        "reasons": reasons,
    }


def _diagnosis_value(
    diagnosis: FailureDiagnosis | dict[str, Any],
    key: str,
) -> Any:
    if isinstance(diagnosis, FailureDiagnosis):
        return getattr(diagnosis, key)
    return diagnosis.get(key)


def _has_progress_postcondition(postconditions: list[str]) -> bool:
    progress_postconditions = {
        "position_changed",
        "door_open",
        "goal_topped_off",
        "object_dropped",
    }
    return bool(progress_postconditions & set(postconditions))


def _is_turn_only_skill(
    semantic_tags: list[str],
    postconditions: list[str],
) -> bool:
    tags = set(semantic_tags)
    if "turn" not in tags:
        return False
    return not _has_progress_postcondition(postconditions)


def _policy_for_failure(failure_type: str) -> str:
    if failure_type in {"step_budget_exhausted", "no_progress"}:
        return "prefer_low_complexity_high_success"
    if failure_type == "looping_or_no_progress":
        return "avoid_repeated_failure_signature"
    if failure_type == "partial_completion":
        return "prefer_missing_subgoal_completion"
    if failure_type == "invalid_action_or_crash":
        return "prefer_safe_high_success"
    return "prefer_general_success"


def _subgoal_for_failure(failure_type: str) -> str:
    if failure_type in {"step_budget_exhausted", "no_progress", "looping_or_no_progress"}:
        return "navigate_to_goal"
    if failure_type == "partial_completion":
        return "open_door"
    if failure_type == "invalid_action_or_crash":
        return "safe_navigation"
    return "navigate_to_goal"


def _context_tags_for_failure(failure_type: str) -> list[str]:
    tags = ["karel"]
    if failure_type in {"step_budget_exhausted", "no_progress", "looping_or_no_progress"}:
        tags.append("navigation")
    if failure_type == "partial_completion":
        tags.extend(["door", "key"])
    if failure_type == "invalid_action_or_crash":
        tags.append("safe")
    return tags
