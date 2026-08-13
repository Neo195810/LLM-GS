"""Versioned execution and reporting for the preregistered ablation matrix."""

from __future__ import annotations

from collections.abc import Iterable
from math import sqrt

from llm_gs.contracts import (
    AblationMatrixSpecification,
    ExperimentManifest,
    ExperimentSpecification,
)
from llm_gs.manifest import resolve_manifest

TASKS = ("CleanHouse", "FourCorners", "DoorKey", "RedBlueDoor")
SEARCH_STRATEGIES = ("single_candidate", "cem", "cebs")
FAILURE_STRATEGIES = ("regenerate", "reflect", "memory_repair", "memory_reflect")


def build_matrix_manifests(
    specification: AblationMatrixSpecification,
) -> tuple[ExperimentManifest, ...]:
    """Resolve the complete paired Frozen-Memory matrix into immutable manifests."""
    manifests = []
    for replicate in specification.replicates:
        for task in TASKS:
            for search_strategy in SEARCH_STRATEGIES:
                for failure_strategy in FAILURE_STRATEGIES:
                    manifest = resolve_manifest(
                        ExperimentSpecification.model_validate(
                            {
                                "display_name": (
                                    f"{specification.display_name}-{replicate}-"
                                    f"{task}-{search_strategy}-{failure_strategy}"
                                ),
                                "task": {"name": task},
                                "seed_suite": specification.seed_suite.model_dump(mode="json"),
                                "search_strategy": {
                                    "name": search_strategy,
                                    "population_size": (
                                        1 if search_strategy == "single_candidate" else 4
                                    ),
                                    "elite_count": 1,
                                },
                                "failure_strategy": {
                                    "name": failure_strategy,
                                    "max_repair_cycles": specification.max_repair_cycles,
                                },
                            }
                        )
                    )
                    manifests.append(
                        manifest.model_copy(
                            update={
                                "search_strategy": {
                                    **manifest.search_strategy,
                                    "seed": specification.search_seed + replicate,
                                    "replicate": replicate,
                                }
                            }
                        )
                    )
    return tuple(manifests)


def matrix_report(reports: Iterable[dict[str, object]]) -> dict[str, object]:
    """Aggregate every supplied arm; Frozen and Online results never share a statistic."""
    records = tuple(reports)
    protocols: dict[str, dict[str, object]] = {}
    for protocol in ("Frozen", "Online"):
        arms = [record for record in records if record.get("protocol") == protocol]
        success_rates = [_success_rate(record) for record in arms]
        protocols[protocol] = {
            "arms": len(arms),
            "fixed_budget_success_rate": sum(success_rates) / len(success_rates)
            if success_rates
            else None,
            "confidence_interval": _confidence_interval(success_rates),
        }
    failure_classes = {"infrastructure": 0, "model_output": 0, "replacements": 0}
    incomplete = 0
    unreported = 0
    for record in records:
        missingness = record.get("missingness", {})
        failures = record.get("failure_classes", {})
        if isinstance(missingness, dict):
            incomplete += int(missingness.get("incomplete_executions", 0))
        if isinstance(failures, dict):
            for key in failure_classes:
                failure_classes[key] += int(failures.get(key, 0))
        if record.get("protocol") not in {"Frozen", "Online"}:
            unreported += 1
    return {
        "arms": len(records),
        "arm_reports": records,
        "protocols": protocols,
        "missingness": {"incomplete_executions": incomplete, "unreported_arms": unreported},
        "exclusions": {"count": 0, "arms": []},
        "failure_classes": failure_classes,
    }


def _wilson_interval(proportion: float, count: int) -> tuple[float, float]:
    z = 1.96
    denominator = 1 + z * z / count
    center = (proportion + z * z / (2 * count)) / denominator
    margin = (
        z * sqrt(proportion * (1 - proportion) / count + z * z / (4 * count * count))
        / denominator
    )
    return center - margin, center + margin


def _confidence_interval(success_rates: list[float]) -> dict[str, float | str | None]:
    if not success_rates:
        return {"method": "wilson-95", "lower": None, "upper": None}
    mean = sum(success_rates) / len(success_rates)
    lower, upper = _wilson_interval(mean, len(success_rates))
    return {"method": "wilson-95", "lower": lower, "upper": upper}


def _success_rate(record: dict[str, object]) -> float:
    value = record["fixed_budget_success_rate"]
    if not isinstance(value, (float, int)):
        raise ValueError("matrix report contains a non-numeric success rate")
    return float(value)
