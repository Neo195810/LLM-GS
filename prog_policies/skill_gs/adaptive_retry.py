from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .adaptive_memory import AdaptiveAttemptMemory
from .evaluator import run_doorkey_mvp
from .failure_detector import FailureDiagnosis, detect_failure
from .replanner import RepairPlan, replan_after_failure
from .skill_ranker import build_default_doorkey_skill_ranking
from .stochastic_perturbation import choose_repair_strategy
from .trace_attribution import analyze_doorkey_trace


def run_doorkey_retry_loop(
    seeds: Iterable[int],
    initial_max_steps: int = 200,
    retry_max_steps: int = 200,
    max_attempts: int = 2,
    skill_store_path: str | Path | None = None,
    attempt_memory_path: str | Path | None = None,
    perturbation_seed: int = 0,
    perturbation_enabled: bool = True,
    replanner_policy: str = "legacy",
) -> dict[str, Any]:
    """Run DoorKey with a minimal adaptive retry wrapper.

    The first Adaptive Core is intentionally conservative: failure detection,
    seeded strategy perturbation, replanning, and attempt memory are explicit,
    while skill-ranking mutation can plug into this wrapper later.
    """

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    seed_list = list(seeds)
    attempts: list[dict[str, Any]] = []
    final_runs: list[dict[str, Any]] = []
    retried_seeds: list[int] = []
    adaptive_memory = AdaptiveAttemptMemory(attempt_memory_path).load()

    for seed in seed_list:
        seed_attempts = []
        next_max_steps = initial_max_steps
        for attempt_index in range(max_attempts):
            max_steps = next_max_steps
            run = run_doorkey_mvp(
                seed=seed,
                max_steps=max_steps,
                skill_store_path=skill_store_path,
            )
            trace_attribution = analyze_doorkey_trace(run, max_steps=max_steps)
            diagnosis = detect_failure(
                run,
                attempt=attempt_index + 1,
                max_steps=max_steps,
            )
            can_retry = not run["success"] and attempt_index < max_attempts - 1
            perturbation = _make_perturbation(
                diagnosis,
                attempt_index + 1,
                seed,
                perturbation_seed,
                perturbation_enabled,
                can_retry,
            )
            skill_ranking = _make_skill_ranking(
                diagnosis,
                perturbation,
                trace_attribution,
                adaptive_memory,
                can_retry,
            )
            repair_plan = _make_repair_plan(
                diagnosis,
                attempt_index + 1,
                max_steps,
                retry_max_steps,
                perturbation,
                skill_ranking,
                trace_attribution,
                replanner_policy,
                can_retry,
            )
            attempt = _summarize_attempt(
                run,
                attempt_index + 1,
                max_steps,
                diagnosis,
                repair_plan,
                skill_ranking,
                trace_attribution,
            )
            attempts.append(attempt)
            seed_attempts.append(attempt)
            adaptive_memory.record_attempt(attempt)

            if run["success"] or attempt_index == max_attempts - 1:
                final_runs.append(run)
                break
            next_max_steps = int(repair_plan.next_attempt["max_steps"])

        if len(seed_attempts) > 1:
            retried_seeds.append(seed)
            adaptive_memory.record_repair_outcome(
                seed=seed,
                failure_type=seed_attempts[0]["diagnosis"]["failure_type"],
                failure_attribution=seed_attempts[0]["trace_attribution"][
                    "attribution"
                ],
                strategy_id=seed_attempts[0]["repair_plan"]["strategy_id"],
                selected_skill_id=seed_attempts[0]["repair_plan"]
                .get("selected_skill", {})
                .get("skill_id"),
                observed_solve_steps=(
                    int(seed_attempts[-1]["steps"])
                    if seed_attempts[-1]["success"]
                    else None
                ),
                from_attempt=seed_attempts[0]["attempt"],
                to_attempt=seed_attempts[-1]["attempt"],
                success=bool(seed_attempts[-1]["success"]),
            )

    adaptive_memory.save()

    successes = [run for run in final_runs if run["success"]]
    success_steps = [run["steps"] for run in successes]
    failed_seeds = [run["seed"] for run in final_runs if not run["success"]]

    result = {
        "task": "DoorKey",
        "seeds": seed_list,
        "adaptive_retry": {
            "enabled": True,
            "max_attempts": max_attempts,
            "initial_max_steps": initial_max_steps,
            "retry_max_steps": retry_max_steps,
            "repair_strategy": "diagnosis_guided_replanning",
            "replanner_policy": replanner_policy,
            "perturbation_enabled": perturbation_enabled,
            "perturbation_seed": perturbation_seed,
        },
        "adaptive_core": {
            "failure_detector": "prog_policies.skill_gs.failure_detector",
            "stochastic_perturbation": "prog_policies.skill_gs.stochastic_perturbation",
            "trace_attribution": "prog_policies.skill_gs.trace_attribution",
            "skill_ranker": "prog_policies.skill_gs.skill_ranker",
            "replanner": "prog_policies.skill_gs.replanner",
            "memory": "prog_policies.skill_gs.adaptive_memory",
        },
        "num_runs": len(final_runs),
        "num_attempts": len(attempts),
        "successes": len(successes),
        "success_rate": len(successes) / len(final_runs) if final_runs else 0.0,
        "failed_seeds": failed_seeds,
        "retried_seeds": retried_seeds,
        "average_steps_successful": (
            sum(success_steps) / len(success_steps) if success_steps else None
        ),
        "critic_decisions": dict(_critic_decisions(final_runs)),
        "attempt_critic_decisions": dict(_attempt_critic_decisions(attempts)),
        "adaptive_memory": adaptive_memory.summary(),
        "attempts": attempts,
        "runs": final_runs,
    }
    if skill_store_path is not None:
        result["skill_memory"] = _summarize_skill_memory(attempts, skill_store_path)
    return result


def _make_perturbation(
    diagnosis: FailureDiagnosis,
    attempt: int,
    seed: int,
    perturbation_seed: int,
    perturbation_enabled: bool,
    can_retry: bool,
) -> dict[str, Any]:
    if perturbation_enabled and can_retry:
        return choose_repair_strategy(
            diagnosis,
            seed=perturbation_seed + seed,
            attempt=attempt,
        )
    return {}


def _make_repair_plan(
    diagnosis: FailureDiagnosis,
    attempt: int,
    max_steps: int,
    retry_max_steps: int,
    perturbation: dict[str, Any],
    skill_ranking: dict[str, Any],
    trace_attribution: dict[str, Any],
    replanner_policy: str,
    can_retry: bool,
) -> RepairPlan:
    return replan_after_failure(
        diagnosis,
        attempt=attempt,
        current_max_steps=max_steps,
        retry_max_steps=retry_max_steps,
        perturbation=perturbation,
        skill_ranking=skill_ranking,
        trace_attribution=trace_attribution,
        replanner_policy=replanner_policy,
        can_retry=can_retry,
    )


def _make_skill_ranking(
    diagnosis: FailureDiagnosis,
    perturbation: dict[str, Any],
    trace_attribution: dict[str, Any],
    adaptive_memory: AdaptiveAttemptMemory,
    can_retry: bool,
) -> dict[str, Any]:
    if diagnosis.success or not can_retry:
        return {}
    skill_feedback = adaptive_memory.skill_feedback(
        trace_attribution.get("attribution")
    )
    return build_default_doorkey_skill_ranking(
        diagnosis,
        perturbation=perturbation,
        skill_feedback=skill_feedback,
    )


def _summarize_attempt(
    run: dict[str, Any],
    attempt: int,
    max_steps: int,
    diagnosis: FailureDiagnosis,
    repair_plan: RepairPlan,
    skill_ranking: dict[str, Any],
    trace_attribution: dict[str, Any],
) -> dict[str, Any]:
    critique = run.get("critique", {})
    summary = {
        "seed": run["seed"],
        "attempt": attempt,
        "max_steps": max_steps,
        "success": run["success"],
        "reward": run["reward"],
        "steps": run["steps"],
        "failure_type": critique.get("failure_type"),
        "repair_operator": critique.get("repair_operator"),
        "repair_hint": critique.get("repair_hint"),
        "trace_attribution": trace_attribution,
        "diagnosis": diagnosis.to_dict(),
        "repair_plan": repair_plan.to_dict(),
    }
    if skill_ranking:
        summary["skill_ranking"] = skill_ranking
    if "skill_memory" in run:
        summary["skill_memory"] = run["skill_memory"]
    return summary


def _critic_decisions(runs: list[dict[str, Any]]) -> Counter[str]:
    return Counter(
        run.get("critique", {}).get("repair_operator", "unknown") for run in runs
    )


def _attempt_critic_decisions(attempts: list[dict[str, Any]]) -> Counter[str]:
    return Counter(attempt.get("repair_operator", "unknown") for attempt in attempts)


def _summarize_skill_memory(
    attempts: list[dict[str, Any]],
    skill_store_path: str | Path,
) -> dict[str, Any]:
    memory_results = [
        attempt["skill_memory"]
        for attempt in attempts
        if "skill_memory" in attempt
    ]
    return {
        "store_path": str(Path(skill_store_path)),
        "stored_skills": sum(item.get("stored_skills", 0) for item in memory_results),
        "updated_skills": sum(item.get("updated_skills", 0) for item in memory_results),
        "skipped_skills": sum(item.get("skipped_skills", 0) for item in memory_results),
        "skipped_runs": sum(
            1
            for item in memory_results
            if item.get("stored_skills", 0) == 0
            and item.get("updated_skills", 0) == 0
        ),
    }
