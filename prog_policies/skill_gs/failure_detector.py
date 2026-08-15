from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class FailureDiagnosis:
    success: bool
    failure_type: str
    severity: str
    failed_stage: str
    recommended_repair: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def detect_failure(
    evaluation: dict[str, Any],
    attempt: int = 1,
    max_steps: int | None = None,
) -> FailureDiagnosis:
    """Normalize evaluator and critic output into an Adaptive Core diagnosis."""

    critique = evaluation.get("critique", {})
    reward = float(evaluation.get("reward", evaluation.get("best_reward", 0.0)))
    steps = int(evaluation.get("steps", len(evaluation.get("trace", []))))
    source_failure_type = critique.get("failure_type", "unknown")
    source_repair = critique.get("repair_operator", "unknown")
    evidence = {
        "task": evaluation.get("task", "unknown"),
        "seed": evaluation.get("seed"),
        "attempt": attempt,
        "reward": reward,
        "steps": steps,
        "max_steps": max_steps,
        "terminated": bool(evaluation.get("terminated", False)),
        "crashed": bool(evaluation.get("crashed", False)),
        "source_failure_type": source_failure_type,
        "source_repair_operator": source_repair,
    }

    if evaluation.get("success"):
        return FailureDiagnosis(
            success=True,
            failure_type="none",
            severity="none",
            failed_stage="completed",
            recommended_repair="store_skill",
            evidence=evidence,
        )

    if evaluation.get("crashed") or source_failure_type == "invalid_action_or_crash":
        return FailureDiagnosis(
            success=False,
            failure_type="invalid_action_or_crash",
            severity="critical",
            failed_stage="attempt_execution",
            recommended_repair="replace_subtree",
            evidence=evidence,
        )

    if max_steps is not None and steps >= max_steps and not evaluation.get("terminated"):
        return FailureDiagnosis(
            success=False,
            failure_type="step_budget_exhausted",
            severity="recoverable",
            failed_stage="attempt_execution",
            recommended_repair="increase_step_budget",
            evidence=evidence,
        )

    if source_failure_type == "looping_or_no_progress":
        return FailureDiagnosis(
            success=False,
            failure_type="looping_or_no_progress",
            severity="recoverable",
            failed_stage="attempt_execution",
            recommended_repair="insert_progress_guard",
            evidence=evidence,
        )

    if source_failure_type == "partial_completion" or 0.0 < reward < 1.0:
        return FailureDiagnosis(
            success=False,
            failure_type="partial_completion",
            severity="recoverable",
            failed_stage="subgoal_transition",
            recommended_repair="insert_missing_subgoal",
            evidence=evidence,
        )

    return FailureDiagnosis(
        success=False,
        failure_type=source_failure_type if source_failure_type != "unknown" else "no_progress",
        severity="recoverable",
        failed_stage="attempt_execution",
        recommended_repair=(
            source_repair if source_repair != "unknown" else "retrieve_alternative_skill"
        ),
        evidence=evidence,
    )
