from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import re
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_ROOT = Path("output") / "skill_gs"
DEFAULT_SKILL_STORE = DEFAULT_OUTPUT_ROOT / "llm_repair_skills_prompt_v4.json"


@dataclass(frozen=True)
class DashboardDatasetConfig:
    dataset_id: str
    label: str
    one_shot_globs: tuple[str, ...]
    repair_summary_paths: tuple[str, ...]


DEFAULT_DATASET_CONFIGS = (
    DashboardDatasetConfig(
        dataset_id="luna_v5_gated",
        label="OpenAI Luna v5 gated",
        one_shot_globs=(
            "llm_generated_seed*_openai_luna_skill_augmented_v5_gated_smoke.json",
        ),
        repair_summary_paths=("llm_repair_seed0_31_v5_gated_summary.json",),
    ),
    DashboardDatasetConfig(
        dataset_id="gemini_3_5_flash_v1",
        label="Gemini 3.5 Flash v1",
        one_shot_globs=(
            "gemini_3_5_flash_v1_seed0_7/llm_generated_seed*_gemini_3_5_flash_v1_smoke.json",
            "gemini_3_5_flash_v1_seed8_15/llm_generated_seed*_gemini_3_5_flash_v1_smoke.json",
            "gemini_3_5_flash_v1_seed16_31/llm_generated_seed*_gemini_3_5_flash_v1_smoke.json",
        ),
        repair_summary_paths=(
            "llm_repair_seed0_7_gemini_3_5_flash_v1_summary.json",
            "llm_repair_seed8_15_gemini_3_5_flash_v1_summary.json",
            "llm_repair_seed16_31_gemini_3_5_flash_v1_summary.json",
        ),
    ),
)


def load_all_dataset_summaries(
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    configs: tuple[DashboardDatasetConfig, ...] = DEFAULT_DATASET_CONFIGS,
) -> list[dict[str, Any]]:
    root = Path(output_root)
    return [load_dataset_summary(root, config) for config in configs]


def load_dataset_summary(
    output_root: str | Path,
    config: DashboardDatasetConfig,
) -> dict[str, Any]:
    root = Path(output_root)
    one_shot_payloads = _load_one_shot_payloads(root, config)
    repair_results = _load_repair_results(root, config)
    seeds = sorted(set(one_shot_payloads) | set(repair_results))

    one_shot_success_seeds = [
        seed
        for seed, payload in sorted(one_shot_payloads.items())
        if bool(payload.get("evaluation", {}).get("success"))
    ]
    repair_success_seeds = [
        seed
        for seed, result in sorted(repair_results.items())
        if bool(result.get("success"))
    ]

    failure_stage_counts: Counter[str] = Counter()
    attribution_counts: Counter[str] = Counter()
    repair_strategy_counts: Counter[str] = Counter()
    repaired_steps = []
    for result in repair_results.values():
        detail = _load_repair_detail(root, result)
        repair_plan = (detail or {}).get("repair_plan") or {}
        attribution = (detail or {}).get("source_attribution") or {}
        strategy_id = repair_plan.get("strategy_id") or result.get("strategy_id")
        if strategy_id:
            repair_strategy_counts[str(strategy_id)] += 1
        if attribution.get("stage_at_end"):
            failure_stage_counts[str(attribution["stage_at_end"])] += 1
        if attribution.get("attribution"):
            attribution_counts[str(attribution["attribution"])] += 1
        steps = (
            (detail or {}).get("repaired_evaluation", {}).get("steps")
            if detail
            else result.get("steps")
        )
        if isinstance(steps, (int, float)):
            repaired_steps.append(float(steps))

    one_shot_steps = [
        float(payload.get("evaluation", {}).get("steps"))
        for payload in one_shot_payloads.values()
        if isinstance(payload.get("evaluation", {}).get("steps"), (int, float))
    ]

    return {
        "dataset_id": config.dataset_id,
        "label": config.label,
        "seeds": seeds,
        "one_shot_successes": len(one_shot_success_seeds),
        "one_shot_total": len(one_shot_payloads),
        "one_shot_success_rate": _rate(len(one_shot_success_seeds), len(one_shot_payloads)),
        "one_shot_success_seeds": one_shot_success_seeds,
        "failed_one_shot_seeds": [
            seed for seed in sorted(one_shot_payloads) if seed not in one_shot_success_seeds
        ],
        "repair_successes": len(repair_success_seeds),
        "repair_total": len(repair_results),
        "repair_success_rate": _rate(len(repair_success_seeds), len(repair_results)),
        "repair_success_seeds": repair_success_seeds,
        "failure_stage_counts": dict(sorted(failure_stage_counts.items())),
        "attribution_counts": dict(sorted(attribution_counts.items())),
        "repair_strategy_counts": dict(sorted(repair_strategy_counts.items())),
        "average_one_shot_steps": _mean(one_shot_steps),
        "average_repaired_steps": _mean(repaired_steps),
    }


def load_seed_detail(
    output_root: str | Path,
    config: DashboardDatasetConfig,
    seed: int,
) -> dict[str, Any]:
    root = Path(output_root)
    one_shot_payloads = _load_one_shot_payloads(root, config)
    repair_results = _load_repair_results(root, config)
    one_shot = one_shot_payloads.get(int(seed)) or {}
    repair_result = repair_results.get(int(seed)) or {}
    repair_detail = _load_repair_detail(root, repair_result) if repair_result else None
    repair_plan = (repair_detail or {}).get("repair_plan")
    source_attribution = (repair_detail or {}).get("source_attribution")
    repaired_evaluation = (repair_detail or {}).get("repaired_evaluation") or {}
    one_shot_evaluation = one_shot.get("evaluation") or {}

    return {
        "dataset_id": config.dataset_id,
        "dataset_label": config.label,
        "seed": int(seed),
        "one_shot_path": _relative_display_path(
            _find_one_shot_files(root, config).get(int(seed)), root
        ),
        "repair_path": _relative_display_path(
            _resolved_optional_path(root, repair_result.get("output_path")), root
        ),
        "environment_status": one_shot.get("environment_status") or {},
        "policy": one_shot.get("policy") or {},
        "policy_actions": list((one_shot.get("policy") or {}).get("actions") or []),
        "one_shot_success": bool(one_shot_evaluation.get("success")),
        "one_shot_reward": one_shot_evaluation.get("reward"),
        "one_shot_steps": one_shot_evaluation.get("steps"),
        "one_shot_trace_rows": trace_to_rows(one_shot_evaluation.get("trace") or []),
        "repair_status": repair_result.get("status") or "not_available",
        "source_attribution": source_attribution,
        "repair_plan": repair_plan,
        "repaired_success": _coalesce_success(
            repaired_evaluation.get("success"),
            repair_result.get("success"),
        ),
        "repaired_reward": repaired_evaluation.get("reward", repair_result.get("reward")),
        "repaired_steps": repaired_evaluation.get("steps", repair_result.get("steps")),
        "repaired_trace_rows": trace_to_rows(repaired_evaluation.get("trace") or []),
    }


def trace_to_rows(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in trace:
        rows.append(
            {
                "step": item.get("step"),
                "action": item.get("action"),
                "agent_before": _format_agent_state(item.get("agent_before")),
                "agent_after": _format_agent_state(item.get("agent_after")),
                "instant_reward": item.get("instant_reward"),
                "total_reward": item.get("total_reward"),
                "door_open": item.get("door_open"),
            }
        )
    return rows


def overview_rows(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for summary in summaries:
        rows.append(
            {
                "dataset": summary["label"],
                "seeds": _seed_span(summary["seeds"]),
                "one_shot_success": _fraction(
                    summary["one_shot_successes"],
                    summary["one_shot_total"],
                ),
                "one_shot_rate": _percent(summary["one_shot_success_rate"]),
                "repair_success": _fraction(
                    summary["repair_successes"],
                    summary["repair_total"],
                ),
                "repair_rate": _percent(summary["repair_success_rate"]),
                "avg_one_shot_steps": _round_optional(summary["average_one_shot_steps"]),
                "avg_repaired_steps": _round_optional(summary["average_repaired_steps"]),
            }
        )
    return rows


def load_skill_rows(skill_store_path: str | Path = DEFAULT_SKILL_STORE) -> list[dict[str, Any]]:
    path = Path(skill_store_path)
    if not path.exists():
        return []
    payload = _read_json(path)
    rows = []
    for skill in payload.get("skills", []):
        metadata = skill.get("metadata") or {}
        source_seeds = metadata.get("source_seeds")
        rows.append(
            {
                "skill_id": skill.get("skill_id", ""),
                "name": skill.get("name", ""),
                "task_family": skill.get("task_family", ""),
                "success_rate": skill.get("success_rate"),
                "num_evaluations": skill.get("num_evaluations", 0),
                "failure_signatures": ", ".join(skill.get("failure_signatures") or []),
                "preconditions": ", ".join(skill.get("preconditions") or []),
                "postconditions": ", ".join(skill.get("postconditions") or []),
                "source_seed_count": _source_seed_count(metadata, source_seeds),
                "example_source_seeds": _example_source_seeds(metadata, source_seeds),
            }
        )
    return sorted(
        rows,
        key=lambda row: (-(row["num_evaluations"] or 0), row["skill_id"]),
    )


def dataset_choices(summaries: list[dict[str, Any]]) -> list[str]:
    return [summary["label"] for summary in summaries]


def seed_choices(summary: dict[str, Any]) -> list[int]:
    return list(summary.get("seeds") or [])


def find_dataset_config_by_label(
    label: str,
    configs: tuple[DashboardDatasetConfig, ...] = DEFAULT_DATASET_CONFIGS,
) -> DashboardDatasetConfig:
    for config in configs:
        if config.label == label:
            return config
    raise ValueError(f"Unknown dataset label: {label}")


def find_summary_by_label(label: str, summaries: list[dict[str, Any]]) -> dict[str, Any]:
    for summary in summaries:
        if summary.get("label") == label:
            return summary
    raise ValueError(f"Unknown dataset label: {label}")


def _load_one_shot_payloads(
    root: Path,
    config: DashboardDatasetConfig,
) -> dict[int, dict[str, Any]]:
    payloads = {}
    for seed, path in _find_one_shot_files(root, config).items():
        payloads[seed] = _read_json(path)
    return payloads


def _find_one_shot_files(
    root: Path,
    config: DashboardDatasetConfig,
) -> dict[int, Path]:
    paths_by_seed = {}
    for pattern in config.one_shot_globs:
        for path in sorted(root.glob(pattern)):
            if not path.is_file():
                continue
            payload = _read_json(path)
            seed = _seed_from_payload_or_name(payload, path)
            if seed is not None:
                paths_by_seed[int(seed)] = path
    return paths_by_seed


def _load_repair_results(
    root: Path,
    config: DashboardDatasetConfig,
) -> dict[int, dict[str, Any]]:
    results = {}
    for summary_path_text in config.repair_summary_paths:
        summary_path = _resolve_path(root, summary_path_text)
        if not summary_path.exists():
            continue
        summary = _read_json(summary_path)
        for result in summary.get("results", []):
            if result.get("seed") is None:
                continue
            seed = int(result["seed"])
            row = dict(result)
            row["_summary_path"] = str(summary_path)
            results[seed] = row
    return results


def _load_repair_detail(root: Path, result: dict[str, Any]) -> dict[str, Any] | None:
    path = _resolved_optional_path(root, result.get("output_path"))
    if path is None or not path.exists():
        return None
    return _read_json(path)


def _resolved_optional_path(root: Path, path_text: str | None) -> Path | None:
    if not path_text:
        return None
    return _resolve_path(root, path_text)


def _resolve_path(root: Path, path_text: str | Path) -> Path:
    path = _normalized_path(path_text)
    if path.is_absolute():
        return path

    candidates = [root / path]
    if root.name == "skill_gs" and root.parent.name == "output":
        candidates.append(root.parent.parent / path)
    candidates.append(Path.cwd() / path)

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _normalized_path(path_text: str | Path) -> Path:
    return Path(str(path_text).replace("\\", "/"))


def _relative_display_path(path: Path | None, root: Path) -> str:
    if path is None:
        return ""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _seed_from_payload_or_name(payload: dict[str, Any], path: Path) -> int | None:
    if payload.get("seed") is not None:
        return int(payload["seed"])
    match = re.search(r"seed(\d+)", path.name)
    if match:
        return int(match.group(1))
    return None


def _format_agent_state(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value))
    return str(value)


def _coalesce_success(*values: Any) -> bool | None:
    for value in values:
        if value is not None:
            return bool(value)
    return None


def _source_seed_count(metadata: dict[str, Any], source_seeds: Any) -> int | str:
    if isinstance(source_seeds, list):
        return len(source_seeds)
    return metadata.get("source_seed_count", "")


def _example_source_seeds(metadata: dict[str, Any], source_seeds: Any) -> str:
    if isinstance(source_seeds, list):
        examples = [str(seed) for seed in source_seeds[:5]]
        if len(source_seeds) > 5:
            examples.append("...")
        return ", ".join(examples)
    examples = metadata.get("example_source_seeds") or []
    if isinstance(examples, list):
        return ", ".join(str(seed) for seed in examples)
    return str(examples) if examples else ""


def _rate(successes: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return successes / total


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _seed_span(seeds: list[int]) -> str:
    if not seeds:
        return ""
    if len(seeds) == 1:
        return str(seeds[0])
    return f"{min(seeds)}-{max(seeds)}"


def _fraction(successes: int, total: int) -> str:
    return f"{successes}/{total}"


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def _round_optional(value: float | None) -> float | str:
    if value is None:
        return ""
    return round(value, 2)
