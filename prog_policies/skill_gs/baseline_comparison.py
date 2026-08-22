from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from .adaptive_retry import run_doorkey_retry_loop
from .evaluator import run_many_doorkey_mvp


DEFAULT_SEARCH_CANDIDATE_MAX_STEPS = (10, 20, 22, 24)
DEFAULT_OURS_RETRY_BUDGET_SCHEDULE = (20, 22, 24)


def run_doorkey_baseline_comparison(
    seeds: Iterable[int],
    initial_max_steps: int = 10,
    search_candidate_max_steps: Sequence[int] = DEFAULT_SEARCH_CANDIDATE_MAX_STEPS,
    ours_retry_budget_schedule: Sequence[int] = DEFAULT_OURS_RETRY_BUDGET_SCHEDULE,
    ours_retry_max_steps: int | None = None,
    ours_max_attempts: int | None = None,
    perturbation_seed: int = 123,
    replanner_policy: str = "attribution_aware",
    include_runs: bool = False,
) -> dict[str, Any]:
    """Compare one-shot, search-style, and adaptive Skill-GS DoorKey baselines.

    The LLM-named baselines are local proxies: they do not call an external LLM.
    This keeps the benchmark reproducible while preserving the relevant
    comparison axes: no repair, candidate search, and adaptive retry/memory.
    """

    seed_list = [int(seed) for seed in seeds]
    candidate_budgets = _normalize_positive_ints(
        search_candidate_max_steps,
        name="search_candidate_max_steps",
    )
    retry_schedule = _normalize_positive_ints(
        ours_retry_budget_schedule,
        name="ours_retry_budget_schedule",
    )
    retry_max_steps = (
        int(ours_retry_max_steps)
        if ours_retry_max_steps is not None
        else (retry_schedule[-1] if retry_schedule else initial_max_steps)
    )
    max_attempts = (
        int(ours_max_attempts)
        if ours_max_attempts is not None
        else max(1, len(retry_schedule) + 1)
    )

    llm_generated = _run_llm_generated_proxy(
        seed_list,
        max_steps=initial_max_steps,
        include_runs=include_runs,
    )
    llm_gs_search = _run_llm_gs_style_search_proxy(
        seed_list,
        candidate_budgets,
        include_runs=include_runs,
    )
    ours = _run_ours_adaptive_skill_gs(
        seed_list,
        initial_max_steps=initial_max_steps,
        retry_max_steps=retry_max_steps,
        retry_budget_schedule=retry_schedule,
        max_attempts=max_attempts,
        perturbation_seed=perturbation_seed,
        replanner_policy=replanner_policy,
        include_runs=include_runs,
    )
    groups = [llm_generated, llm_gs_search, ours]

    return {
        "task": "DoorKey",
        "fairness": {
            "seeds": seed_list,
            "shared_task": "DoorKey",
            "shared_environment": "prog_policies.karel_tasks.DoorKey",
            "shared_evaluator": "prog_policies.skill_gs.evaluator.run_doorkey_mvp",
            "external_llm_calls": False,
            "max_allowed_execution_budget": max(
                [initial_max_steps, retry_max_steps, *candidate_budgets, *retry_schedule]
            ),
            "notes": [
                "LLM-generated is represented as a reproducible one-shot local proxy.",
                "LLM-GS-style search evaluates fixed candidate programs/budgets without adaptive memory.",
                "Ours uses attribution-aware adaptive retry and retry budget schedule.",
            ],
        },
        "groups": groups,
        "comparison_table": [_comparison_row(group) for group in groups],
    }


def _run_llm_generated_proxy(
    seeds: list[int],
    max_steps: int,
    include_runs: bool,
) -> dict[str, Any]:
    evaluation = run_many_doorkey_mvp(seeds=seeds, max_steps=max_steps)
    return _summarize_group(
        name="llm_generated",
        label="LLM-generated one-shot proxy",
        strategy_family="one_shot_program",
        evaluation=evaluation,
        evaluation_count=len(seeds),
        max_execution_budget=max_steps,
        repair_enabled=False,
        memory_enabled=False,
        include_runs=include_runs,
        extra={
            "proxy": True,
            "max_steps": max_steps,
            "description": "Single generated program/policy with no search and no repair.",
        },
    )


def _run_llm_gs_style_search_proxy(
    seeds: list[int],
    candidate_budgets: list[int],
    include_runs: bool,
) -> dict[str, Any]:
    candidate_records = []
    for index, max_steps in enumerate(candidate_budgets, start=1):
        evaluation = run_many_doorkey_mvp(seeds=seeds, max_steps=max_steps)
        candidate_records.append(
            {
                "candidate_id": f"candidate_{index:02d}",
                "max_steps": max_steps,
                "evaluation": evaluation,
                "summary": _candidate_summary(
                    candidate_id=f"candidate_{index:02d}",
                    max_steps=max_steps,
                    evaluation=evaluation,
                ),
            }
        )

    selected = max(candidate_records, key=_candidate_score)
    group = _summarize_group(
        name="llm_gs_style_search",
        label="LLM-GS-style candidate search proxy",
        strategy_family="candidate_search",
        evaluation=selected["evaluation"],
        evaluation_count=len(seeds) * len(candidate_records),
        max_execution_budget=max(candidate_budgets),
        repair_enabled=False,
        memory_enabled=False,
        include_runs=include_runs,
        extra={
            "proxy": True,
            "search_space": {
                "candidate_count": len(candidate_records),
                "candidate_max_steps": candidate_budgets,
            },
            "selected_candidate": selected["summary"],
            "candidate_results": [record["summary"] for record in candidate_records],
        },
    )
    return group


def _run_ours_adaptive_skill_gs(
    seeds: list[int],
    initial_max_steps: int,
    retry_max_steps: int,
    retry_budget_schedule: list[int],
    max_attempts: int,
    perturbation_seed: int,
    replanner_policy: str,
    include_runs: bool,
) -> dict[str, Any]:
    evaluation = run_doorkey_retry_loop(
        seeds=seeds,
        initial_max_steps=initial_max_steps,
        retry_max_steps=retry_max_steps,
        retry_budget_schedule=retry_budget_schedule,
        max_attempts=max_attempts,
        perturbation_seed=perturbation_seed,
        replanner_policy=replanner_policy,
    )
    max_execution_budget = max([initial_max_steps, retry_max_steps, *retry_budget_schedule])
    return _summarize_group(
        name="ours_adaptive_skill_gs",
        label="Ours: Adaptive Skill-GS",
        strategy_family="adaptive_retry",
        evaluation=evaluation,
        evaluation_count=evaluation["num_attempts"],
        max_execution_budget=max_execution_budget,
        repair_enabled=True,
        memory_enabled=True,
        include_runs=include_runs,
        extra={
            "adaptive_retry": evaluation["adaptive_retry"],
            "adaptive_memory": evaluation["adaptive_memory"],
            "retried_seeds": evaluation["retried_seeds"],
            "attempt_critic_decisions": evaluation["attempt_critic_decisions"],
        },
    )


def _summarize_group(
    name: str,
    label: str,
    strategy_family: str,
    evaluation: dict[str, Any],
    evaluation_count: int,
    max_execution_budget: int,
    repair_enabled: bool,
    memory_enabled: bool,
    include_runs: bool,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    group = {
        "name": name,
        "label": label,
        "strategy_family": strategy_family,
        "num_runs": evaluation["num_runs"],
        "successes": evaluation["successes"],
        "success_rate": evaluation["success_rate"],
        "failed_seeds": evaluation["failed_seeds"],
        "average_steps_successful": evaluation["average_steps_successful"],
        "critic_decisions": evaluation["critic_decisions"],
        "evaluation_count": evaluation_count,
        "max_execution_budget": max_execution_budget,
        "repair_enabled": repair_enabled,
        "memory_enabled": memory_enabled,
    }
    if include_runs:
        group["runs"] = evaluation["runs"]
    if extra:
        group.update(extra)
    return group


def _candidate_summary(
    candidate_id: str,
    max_steps: int,
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "max_steps": max_steps,
        "num_runs": evaluation["num_runs"],
        "successes": evaluation["successes"],
        "success_rate": evaluation["success_rate"],
        "failed_seeds": evaluation["failed_seeds"],
        "average_steps_successful": evaluation["average_steps_successful"],
    }


def _candidate_score(record: dict[str, Any]) -> tuple[float, int, int, float, int]:
    summary = record["summary"]
    average_steps = summary["average_steps_successful"]
    average_steps_penalty = (
        float("inf") if average_steps is None else float(average_steps)
    )
    return (
        float(summary["success_rate"]),
        int(summary["successes"]),
        -len(summary["failed_seeds"]),
        -average_steps_penalty,
        -int(summary["max_steps"]),
    )


def _comparison_row(group: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": group["name"],
        "strategy_family": group["strategy_family"],
        "successes": group["successes"],
        "num_runs": group["num_runs"],
        "success_rate": group["success_rate"],
        "failed_seeds": group["failed_seeds"],
        "average_steps_successful": group["average_steps_successful"],
        "evaluation_count": group["evaluation_count"],
        "max_execution_budget": group["max_execution_budget"],
        "repair_enabled": group["repair_enabled"],
        "memory_enabled": group["memory_enabled"],
    }


def _normalize_positive_ints(values: Sequence[int], name: str) -> list[int]:
    normalized = [int(value) for value in values]
    if not normalized:
        raise ValueError(f"{name} must contain at least one value")
    if any(value < 1 for value in normalized):
        raise ValueError(f"{name} values must be positive integers")
    return normalized
