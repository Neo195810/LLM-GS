from __future__ import annotations

import random
from typing import Any

from .failure_detector import FailureDiagnosis


REPAIR_CANDIDATES = {
    "step_budget_exhausted": [
        ("increase_step_budget", 0.85),
        ("retrieve_alternative_skill", 0.15),
    ],
    "no_progress": [
        ("retrieve_alternative_skill", 0.65),
        ("increase_step_budget", 0.35),
    ],
    "looping_or_no_progress": [
        ("insert_progress_guard", 0.7),
        ("retrieve_alternative_skill", 0.3),
    ],
    "partial_completion": [
        ("insert_missing_subgoal", 0.8),
        ("retrieve_alternative_skill", 0.2),
    ],
    "invalid_action_or_crash": [
        ("replace_subtree", 0.8),
        ("retrieve_alternative_skill", 0.2),
    ],
}


def choose_repair_strategy(
    diagnosis: FailureDiagnosis | dict[str, Any],
    seed: int = 0,
    attempt: int = 1,
) -> dict[str, Any]:
    """Choose a seeded repair perturbation from diagnosis-specific candidates."""

    failure_type = _diagnosis_value(diagnosis, "failure_type")
    recommended = _diagnosis_value(diagnosis, "recommended_repair")
    candidates = list(
        REPAIR_CANDIDATES.get(
            failure_type,
            [(recommended or "retrieve_alternative_skill", 1.0)],
        )
    )
    rng = random.Random(f"{seed}:{attempt}:{failure_type}")
    draw = rng.random()
    strategy = _weighted_choice(candidates, draw)
    return {
        "strategy_id": strategy,
        "failure_type": failure_type,
        "attempt": attempt,
        "seed": seed,
        "random_value": draw,
        "candidates": [
            {"strategy_id": item[0], "weight": item[1]} for item in candidates
        ],
    }


def _diagnosis_value(diagnosis: FailureDiagnosis | dict[str, Any], key: str) -> Any:
    if isinstance(diagnosis, FailureDiagnosis):
        return getattr(diagnosis, key)
    return diagnosis.get(key)


def _weighted_choice(candidates: list[tuple[str, float]], draw: float) -> str:
    total = sum(weight for _, weight in candidates)
    threshold = draw * total
    cumulative = 0.0
    for strategy_id, weight in candidates:
        cumulative += weight
        if threshold <= cumulative:
            return strategy_id
    return candidates[-1][0]
