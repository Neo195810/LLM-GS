from __future__ import annotations

from collections import Counter
from typing import Any

from .schemas import Critique


class CriticRepairAgent:
    """Turn evaluator output into structured repair signals."""

    def analyze(self, evaluation: dict[str, Any]) -> Critique:
        success = bool(evaluation.get("success", False))
        reward = float(evaluation.get("reward", evaluation.get("best_reward", 0.0)))
        trace = evaluation.get("trace", [])
        task = str(evaluation.get("task", "unknown"))

        if success or reward >= 1.0:
            return Critique(
                success=True,
                failure_type="none",
                failed_subgoal=None,
                failed_node_id=None,
                repair_operator="store_skill",
                repair_hint="Store the successful AST subtree with its task context.",
                evidence={"reward": reward, "task": task},
            )

        if evaluation.get("crashed", False) or _trace_has(trace, "crash"):
            return Critique(
                success=False,
                failure_type="invalid_action_or_crash",
                failed_subgoal=evaluation.get("current_subgoal"),
                failed_node_id=evaluation.get("failed_node_id"),
                repair_operator="replace_subtree",
                repair_hint="Replace the failed subtree with a type-compatible safe navigation skill.",
                evidence={"reward": reward, "task": task},
            )

        if _looks_repetitive(trace):
            return Critique(
                success=False,
                failure_type="looping_or_no_progress",
                failed_subgoal=evaluation.get("current_subgoal"),
                failed_node_id=evaluation.get("failed_node_id"),
                repair_operator="insert_progress_guard",
                repair_hint="Add a perception guard or swap in an exploration/navigation skill.",
                evidence={"reward": reward, "trace_length": len(trace), "task": task},
            )

        if 0.0 < reward < 1.0:
            return Critique(
                success=False,
                failure_type="partial_completion",
                failed_subgoal=evaluation.get("current_subgoal", "second_stage"),
                failed_node_id=evaluation.get("failed_node_id"),
                repair_operator="insert_missing_subgoal",
                repair_hint="Keep the successful prefix and insert a retrieved skill for the next subgoal.",
                evidence={"reward": reward, "task": task},
            )

        return Critique(
            success=False,
            failure_type="no_progress",
            failed_subgoal=evaluation.get("current_subgoal"),
            failed_node_id=evaluation.get("failed_node_id"),
            repair_operator="retrieve_alternative_skill",
            repair_hint="Retrieve a simpler skill with matching preconditions before global mutation.",
            evidence={"reward": reward, "task": task},
        )


def _trace_has(trace: list[Any], needle: str) -> bool:
    text = " ".join(str(item).lower() for item in trace)
    return needle.lower() in text


def _looks_repetitive(trace: list[Any]) -> bool:
    if len(trace) < 6:
        return False
    keys = [str(item) for item in trace]
    counts = Counter(keys)
    _, most_common_count = counts.most_common(1)[0]
    return most_common_count >= max(4, len(trace) // 2)
