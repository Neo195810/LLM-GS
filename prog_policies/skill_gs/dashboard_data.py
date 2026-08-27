from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import html
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
    environment_status = one_shot.get("environment_status") or {}
    one_shot_trace = one_shot_evaluation.get("trace") or []
    repaired_trace = repaired_evaluation.get("trace") or []

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
        "environment_status": environment_status,
        "policy": one_shot.get("policy") or {},
        "policy_actions": list((one_shot.get("policy") or {}).get("actions") or []),
        "one_shot_success": bool(one_shot_evaluation.get("success")),
        "one_shot_reward": one_shot_evaluation.get("reward"),
        "one_shot_steps": one_shot_evaluation.get("steps"),
        "one_shot_trace": one_shot_trace,
        "one_shot_trace_rows": trace_to_rows(one_shot_trace),
        "repair_status": repair_result.get("status") or "not_available",
        "source_attribution": source_attribution,
        "repair_plan": repair_plan,
        "repaired_success": _coalesce_success(
            repaired_evaluation.get("success"),
            repair_result.get("success"),
        ),
        "repaired_reward": repaired_evaluation.get("reward", repair_result.get("reward")),
        "repaired_steps": repaired_evaluation.get("steps", repair_result.get("steps")),
        "repaired_trace": repaired_trace,
        "repaired_trace_rows": trace_to_rows(repaired_trace),
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


def render_trace_svg(
    environment_status: dict[str, Any],
    trace: list[dict[str, Any]],
    title: str = "Trace",
    *,
    current_step_index: int | None = None,
) -> str:
    environment_status = environment_status or {}
    full_trace = trace or []
    selected_step_index = _clamped_trace_index(full_trace, current_step_index)
    trace = _trace_prefix(full_trace, selected_step_index)
    current_step = full_trace[selected_step_index] if selected_step_index is not None else None
    grid_rows, grid_cols = _trace_grid_size(environment_status, full_trace)
    cell_size = 34
    padding = 18
    title_height = 30
    legend_height = 22
    width = padding * 2 + grid_cols * cell_size
    height = title_height + padding + grid_rows * cell_size + legend_height
    grid_top = title_height

    walls = _cell_set(environment_status.get("wall_cells"))
    doors = _cell_set(environment_status.get("door_cells"))
    key_position = _cell_position(environment_status.get("key_position"))
    goal_position = _cell_position(environment_status.get("goal_position"))
    positions = _trace_positions(environment_status, trace)

    escaped_title = html.escape(title)
    escaped_action = html.escape(str((current_step or {}).get("action") or ""), quote=True)
    current_step_number = (
        str((current_step or {}).get("step") or selected_step_index + 1)
        if selected_step_index is not None
        else ""
    )
    player_attrs = (
        f' data-current-step="{current_step_number}"'
        f' data-visible-step-count="{len(trace)}"'
        f' data-current-action="{escaped_action}"'
    )
    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="{escaped_title}" '
            f'{player_attrs} '
            f'style="width:100%;max-width:{width}px;height:auto;">'
        ),
        f"<title>{escaped_title}</title>",
        f"<desc>{escaped_title} on the DoorKey grid.</desc>",
        '<rect width="100%" height="100%" rx="8" fill="#f8fafc"/>',
        (
            f'<text x="{padding}" y="20" fill="#111827" '
            f'font-family="Arial, sans-serif" font-size="13" '
            f'font-weight="700">{escaped_title}</text>'
        ),
    ]

    for row in range(grid_rows):
        for col in range(grid_cols):
            cell_kind, fill, text = _cell_style((row, col), walls, doors, key_position, goal_position)
            x = padding + col * cell_size
            y = grid_top + row * cell_size
            parts.append(
                (
                    f'<rect data-cell="{cell_kind}" x="{x}" y="{y}" '
                    f'width="{cell_size}" height="{cell_size}" fill="{fill}" '
                    f'stroke="#cbd5e1" stroke-width="1"/>'
                )
            )
            if text:
                parts.append(
                    (
                        f'<text x="{x + cell_size / 2:.1f}" y="{y + cell_size / 2 + 5:.1f}" '
                        f'fill="#111827" font-family="Arial, sans-serif" '
                        f'font-size="12" font-weight="700" text-anchor="middle">{text}</text>'
                    )
                )

    if positions:
        points = " ".join(
            f"{_cell_center(position, padding, grid_top, cell_size)[0]:.1f},"
            f"{_cell_center(position, padding, grid_top, cell_size)[1]:.1f}"
            for position in positions
        )
        if len(positions) > 1:
            parts.append(
                (
                    f'<polyline data-layer="path" points="{points}" fill="none" '
                    f'stroke="#2563eb" stroke-width="4" stroke-linecap="round" '
                    f'stroke-linejoin="round" opacity="0.86"/>'
                )
            )
        for step_index, position in _condensed_path_points(positions):
            cx, cy = _cell_center(position, padding, grid_top, cell_size)
            parts.append(
                (
                    f'<circle data-layer="step" cx="{cx:.1f}" cy="{cy:.1f}" '
                    f'r="5" fill="#1d4ed8" opacity="0.78"/>'
                )
            )
            if 0 < step_index < len(positions) - 1:
                parts.append(
                    (
                        f'<text x="{cx:.1f}" y="{cy - 8:.1f}" fill="#1f2937" '
                        f'font-family="Arial, sans-serif" font-size="9" '
                        f'text-anchor="middle">{step_index}</text>'
                    )
                )
        _append_marker(parts, "start", positions[0], padding, grid_top, cell_size, "S", "#0f766e")
        _append_marker(parts, "end", positions[-1], padding, grid_top, cell_size, "E", "#dc2626")
        if current_step is not None:
            _append_current_agent(
                parts,
                current_step.get("agent_after"),
                padding,
                grid_top,
                cell_size,
            )
    else:
        parts.append(
            (
                f'<text x="{width / 2:.1f}" y="{height / 2:.1f}" fill="#475569" '
                f'font-family="Arial, sans-serif" font-size="13" text-anchor="middle">'
                "No trace available</text>"
            )
        )

    legend_y = title_height + padding + grid_rows * cell_size + 15
    parts.append(
        (
            f'<text x="{padding}" y="{legend_y}" fill="#334155" '
            f'font-family="Arial, sans-serif" font-size="11">'
            "S start | K key | D door | G goal | E end</text>"
        )
    )
    parts.append("</svg>")
    return "".join(parts)


def render_trace_step_svg(
    environment_status: dict[str, Any],
    trace: list[dict[str, Any]],
    step_index: int,
    title: str = "Trace Player",
) -> str:
    return render_trace_svg(
        environment_status,
        trace,
        title=title,
        current_step_index=step_index,
    )


def trace_step_summary(
    trace: list[dict[str, Any]],
    step_index: int,
    trace_label: str = "Trace",
) -> str:
    trace = trace or []
    current_index = _clamped_trace_index(trace, step_index)
    if current_index is None:
        return f"{trace_label}: no trace available."

    item = trace[current_index]
    step_number = item.get("step") or current_index + 1
    action = item.get("action") or "unknown"
    before = _format_agent_state(item.get("agent_before"))
    after = _format_agent_state(item.get("agent_after"))
    instant_reward = item.get("instant_reward")
    total_reward = item.get("total_reward")
    door_open = item.get("door_open")
    return (
        f"{trace_label} | Step {step_number}/{len(trace)}: {action} | "
        f"{before} -> {after} | reward {instant_reward} | "
        f"total {total_reward} | door_open {door_open}"
    )


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


def _clamped_trace_index(
    trace: list[dict[str, Any]],
    step_index: int | None,
) -> int | None:
    if step_index is None or not trace:
        return None
    try:
        index = int(step_index)
    except (TypeError, ValueError):
        index = 0
    return min(max(index, 0), len(trace) - 1)


def _trace_prefix(
    trace: list[dict[str, Any]],
    selected_step_index: int | None,
) -> list[dict[str, Any]]:
    if selected_step_index is None:
        return trace
    return trace[: selected_step_index + 1]


def _trace_grid_size(
    environment_status: dict[str, Any],
    trace: list[dict[str, Any]],
) -> tuple[int, int]:
    grid_size = environment_status.get("grid_size")
    if isinstance(grid_size, (list, tuple)) and len(grid_size) >= 2:
        try:
            return max(1, int(grid_size[0])), max(1, int(grid_size[1]))
        except (TypeError, ValueError):
            pass

    positions = []
    positions.extend(_cell_set(environment_status.get("wall_cells")))
    positions.extend(_cell_set(environment_status.get("door_cells")))
    for key in ("key_position", "goal_position"):
        position = _cell_position(environment_status.get(key))
        if position is not None:
            positions.append(position)
    agent_position = _cell_position((environment_status.get("agent") or {}).get("position"))
    if agent_position is not None:
        positions.append(agent_position)
    positions.extend(_trace_positions(environment_status, trace))
    if not positions:
        return 1, 1
    return (
        max(row for row, _ in positions) + 1,
        max(col for _, col in positions) + 1,
    )


def _cell_set(values: Any) -> set[tuple[int, int]]:
    if not isinstance(values, list):
        return set()
    cells = set()
    for value in values:
        position = _cell_position(value)
        if position is not None:
            cells.add(position)
    return cells


def _cell_position(value: Any) -> tuple[int, int] | None:
    if isinstance(value, dict):
        value = value.get("position")
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        return int(value[0]), int(value[1])
    except (TypeError, ValueError):
        return None


def _trace_positions(
    environment_status: dict[str, Any],
    trace: list[dict[str, Any]],
) -> list[tuple[int, int]]:
    positions = []
    if trace:
        first_position = _cell_position(trace[0].get("agent_before"))
        if first_position is not None:
            positions.append(first_position)
        for item in trace:
            position = _cell_position(item.get("agent_after"))
            if position is not None:
                positions.append(position)
    if positions:
        return positions
    agent_position = _cell_position((environment_status.get("agent") or {}).get("position"))
    return [agent_position] if agent_position is not None else []


def _cell_style(
    position: tuple[int, int],
    walls: set[tuple[int, int]],
    doors: set[tuple[int, int]],
    key_position: tuple[int, int] | None,
    goal_position: tuple[int, int] | None,
) -> tuple[str, str, str]:
    if position == key_position:
        return "key", "#facc15", "K"
    if position == goal_position:
        return "goal", "#86efac", "G"
    if position in doors:
        return "door", "#fb923c", "D"
    if position in walls:
        return "wall", "#334155", ""
    return "empty", "#ffffff", ""


def _cell_center(
    position: tuple[int, int],
    padding: int,
    grid_top: int,
    cell_size: int,
) -> tuple[float, float]:
    row, col = position
    return (
        padding + col * cell_size + cell_size / 2,
        grid_top + row * cell_size + cell_size / 2,
    )


def _condensed_path_points(positions: list[tuple[int, int]]) -> list[tuple[int, tuple[int, int]]]:
    condensed = []
    previous = None
    for index, position in enumerate(positions):
        if position != previous:
            condensed.append((index, position))
            previous = position
    return condensed


def _append_marker(
    parts: list[str],
    marker_id: str,
    position: tuple[int, int],
    padding: int,
    grid_top: int,
    cell_size: int,
    label: str,
    fill: str,
) -> None:
    cx, cy = _cell_center(position, padding, grid_top, cell_size)
    parts.append(
        (
            f'<circle data-marker="{marker_id}" cx="{cx:.1f}" cy="{cy:.1f}" '
            f'r="10" fill="{fill}" stroke="#ffffff" stroke-width="2"/>'
        )
    )
    parts.append(
        (
            f'<text x="{cx:.1f}" y="{cy + 4:.1f}" fill="#ffffff" '
            f'font-family="Arial, sans-serif" font-size="10" font-weight="700" '
            f'text-anchor="middle">{label}</text>'
        )
    )


def _append_current_agent(
    parts: list[str],
    agent_state: Any,
    padding: int,
    grid_top: int,
    cell_size: int,
) -> None:
    position = _cell_position(agent_state)
    if position is None:
        return
    direction_index = _direction_index(agent_state)
    cx, cy = _cell_center(position, padding, grid_top, cell_size)
    angle = {0: 0, 1: 90, 2: 180, 3: 270}.get(direction_index, 0)
    parts.append(
        (
            f'<g data-marker="current-agent" data-direction-index="{direction_index}" '
            f'transform="translate({cx:.1f} {cy:.1f}) rotate({angle})">'
            '<path d="M 0 -13 L 9 10 L 0 5 L -9 10 Z" fill="#7c3aed" '
            'stroke="#ffffff" stroke-width="1.5"/>'
            "</g>"
        )
    )


def _direction_index(value: Any) -> int:
    if isinstance(value, dict):
        value = value.get("direction_index")
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            return int(value[2])
        except (TypeError, ValueError):
            return 0
    return 0


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
