from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

LOCALHOST_PROXY_BYPASS = ("localhost", "127.0.0.1", "::1")


def _ensure_localhost_proxy_bypass() -> None:
    for key in ("NO_PROXY", "no_proxy"):
        current = [
            item.strip()
            for item in os.environ.get(key, "").split(",")
            if item.strip()
        ]
        for host in LOCALHOST_PROXY_BYPASS:
            if host not in current:
                current.append(host)
        os.environ[key] = ",".join(current)
    os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")


_ensure_localhost_proxy_bypass()

try:
    import gradio as gr
except ModuleNotFoundError:
    gr = None

try:
    import pandas as pd
except ModuleNotFoundError:
    pd = None

from prog_policies.skill_gs.dashboard_data import (
    DEFAULT_DATASET_CONFIGS,
    DEFAULT_SKILL_STORE,
    DashboardDatasetConfig,
    dataset_choices,
    find_dataset_config_by_label,
    find_summary_by_label,
    load_all_dataset_summaries,
    load_seed_detail,
    load_skill_rows,
    overview_rows,
    seed_choices,
)


DEFAULT_OUTPUT_ROOT = REPO_ROOT / "output" / "skill_gs"
DEFAULT_SKILL_STORE_PATH = REPO_ROOT / DEFAULT_SKILL_STORE

TRACE_COLUMNS = [
    "step",
    "action",
    "agent_before",
    "agent_after",
    "instant_reward",
    "total_reward",
    "door_open",
]
OVERVIEW_COLUMNS = [
    "dataset",
    "seeds",
    "one_shot_success",
    "one_shot_rate",
    "repair_success",
    "repair_rate",
    "avg_one_shot_steps",
    "avg_repaired_steps",
]
SKILL_COLUMNS = [
    "skill_id",
    "name",
    "task_family",
    "success_rate",
    "num_evaluations",
    "failure_signatures",
    "preconditions",
    "postconditions",
    "source_seed_count",
    "example_source_seeds",
]


def build_app(
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    skill_store_path: str | Path = DEFAULT_SKILL_STORE_PATH,
    dataset_configs: tuple[DashboardDatasetConfig, ...] = DEFAULT_DATASET_CONFIGS,
):
    if gr is None:
        raise RuntimeError("Gradio is not installed. Install requirements.txt before launching.")
    if pd is None:
        raise RuntimeError("Pandas is not installed. Install requirements.txt before launching.")

    output_root = Path(output_root)
    skill_store_path = Path(skill_store_path)
    summaries = _safe_summaries(output_root, dataset_configs)
    labels = dataset_choices(summaries)
    initial_dataset = labels[0] if labels else ""
    initial_seed = _initial_seed(summaries, initial_dataset)

    css = """
    :root { --skill-ink: #1f2933; --skill-paper: #f7f7f4; --skill-line: #d9ded8; }
    html, body, .gradio-container { color: var(--skill-ink) !important; }
    .gradio-container { background: var(--skill-paper); }
    .compact-table { min-height: 220px; }
    .trace-table { min-height: 320px; }
    .code-panel textarea { font-family: 'IBM Plex Mono', 'Courier New', monospace !important; }
    """

    with gr.Blocks(
        title="Skill-GS Demo Dashboard",
        css=css,
        analytics_enabled=False,
    ) as app:
        gr.Markdown("# Skill-GS Demo Dashboard")
        with gr.Row():
            output_root_box = gr.Textbox(
                value=str(output_root),
                label="JSON Root",
                scale=4,
            )
            skill_store_box = gr.Textbox(
                value=str(skill_store_path),
                label="Skill Store",
                scale=4,
            )
            refresh_button = gr.Button("Refresh", variant="primary", scale=1)

        overview_table = gr.Dataframe(
            value=_df(overview_rows(summaries), OVERVIEW_COLUMNS),
            headers=OVERVIEW_COLUMNS,
            label="Overview",
            interactive=False,
            elem_classes=["compact-table"],
        )

        with gr.Tabs():
            with gr.Tab("Seed Inspector"):
                with gr.Row():
                    dataset_dropdown = gr.Dropdown(
                        choices=labels,
                        value=initial_dataset,
                        label="Dataset",
                    )
                    seed_dropdown = gr.Dropdown(
                        choices=_seed_choices_for_label(summaries, initial_dataset),
                        value=initial_seed,
                        label="Seed",
                    )
                seed_status = gr.Markdown(_status_text({}))
                with gr.Row():
                    environment_state = gr.Code(
                        value="{}",
                        language="json",
                        label="Environment State",
                        elem_classes=["code-panel"],
                    )
                    policy_actions = gr.Code(
                        value="{}",
                        language="json",
                        label="Policy Actions",
                        elem_classes=["code-panel"],
                    )
                with gr.Row():
                    failure_attribution = gr.Code(
                        value="{}",
                        language="json",
                        label="Failure Attribution",
                        elem_classes=["code-panel"],
                    )
                    repair_plan = gr.Code(
                        value="{}",
                        language="json",
                        label="Repair Plan",
                        elem_classes=["code-panel"],
                    )
                with gr.Row():
                    one_shot_trace = gr.Dataframe(
                        value=_df([], TRACE_COLUMNS),
                        headers=TRACE_COLUMNS,
                        label="One-shot Trace",
                        interactive=False,
                        elem_classes=["trace-table"],
                    )
                    repaired_trace = gr.Dataframe(
                        value=_df([], TRACE_COLUMNS),
                        headers=TRACE_COLUMNS,
                        label="Repaired Trace",
                        interactive=False,
                        elem_classes=["trace-table"],
                    )

            with gr.Tab("Skill Memory"):
                skill_table = gr.Dataframe(
                    value=_df(load_skill_rows(skill_store_path), SKILL_COLUMNS),
                    headers=SKILL_COLUMNS,
                    label="Skill Memory",
                    interactive=False,
                    elem_classes=["compact-table"],
                )

        if initial_dataset and initial_seed is not None:
            initial_outputs = _seed_outputs(
                output_root,
                dataset_configs,
                initial_dataset,
                initial_seed,
            )
            seed_status.value = initial_outputs[0]
            environment_state.value = initial_outputs[1]
            policy_actions.value = initial_outputs[2]
            failure_attribution.value = initial_outputs[3]
            repair_plan.value = initial_outputs[4]
            one_shot_trace.value = initial_outputs[5]
            repaired_trace.value = initial_outputs[6]

        refresh_button.click(
            _refresh,
            [output_root_box, skill_store_box],
            [
                overview_table,
                dataset_dropdown,
                seed_dropdown,
                skill_table,
                seed_status,
                environment_state,
                policy_actions,
                failure_attribution,
                repair_plan,
                one_shot_trace,
                repaired_trace,
            ],
            queue=False,
        )
        dataset_dropdown.change(
            _change_dataset,
            [output_root_box, dataset_dropdown],
            [
                seed_dropdown,
                seed_status,
                environment_state,
                policy_actions,
                failure_attribution,
                repair_plan,
                one_shot_trace,
                repaired_trace,
            ],
            queue=False,
        )
        seed_dropdown.change(
            _change_seed,
            [output_root_box, dataset_dropdown, seed_dropdown],
            [
                seed_status,
                environment_state,
                policy_actions,
                failure_attribution,
                repair_plan,
                one_shot_trace,
                repaired_trace,
            ],
            queue=False,
        )
    return app


def _refresh(output_root_text: str, skill_store_text: str):
    output_root = Path(output_root_text)
    summaries = _safe_summaries(output_root, DEFAULT_DATASET_CONFIGS)
    labels = dataset_choices(summaries)
    dataset_label = labels[0] if labels else ""
    selected_seed = _initial_seed(summaries, dataset_label)
    seed_options = _seed_choices_for_label(summaries, dataset_label)
    detail_outputs = _seed_outputs(output_root, DEFAULT_DATASET_CONFIGS, dataset_label, selected_seed)
    return (
        _df(overview_rows(summaries), OVERVIEW_COLUMNS),
        gr.update(choices=labels, value=dataset_label),
        gr.update(choices=seed_options, value=selected_seed),
        _df(load_skill_rows(Path(skill_store_text)), SKILL_COLUMNS),
        *detail_outputs,
    )


def _change_dataset(output_root_text: str, dataset_label: str):
    output_root = Path(output_root_text)
    summaries = _safe_summaries(output_root, DEFAULT_DATASET_CONFIGS)
    selected_seed = _initial_seed(summaries, dataset_label)
    detail_outputs = _seed_outputs(output_root, DEFAULT_DATASET_CONFIGS, dataset_label, selected_seed)
    return (
        gr.update(
            choices=_seed_choices_for_label(summaries, dataset_label),
            value=selected_seed,
        ),
        *detail_outputs,
    )


def _change_seed(output_root_text: str, dataset_label: str, seed: int | str | None):
    return _seed_outputs(Path(output_root_text), DEFAULT_DATASET_CONFIGS, dataset_label, seed)


def _seed_outputs(
    output_root: Path,
    dataset_configs: tuple[DashboardDatasetConfig, ...],
    dataset_label: str,
    seed: int | str | None,
):
    if not dataset_label or seed in (None, ""):
        return _empty_seed_outputs()
    try:
        config = find_dataset_config_by_label(dataset_label, dataset_configs)
        detail = load_seed_detail(output_root, config, int(seed))
        return (
            _status_text(detail),
            _json_text(detail.get("environment_status")),
            _json_text(
                {
                    "policy": detail.get("policy"),
                    "actions": detail.get("policy_actions"),
                    "one_shot_path": detail.get("one_shot_path"),
                }
            ),
            _json_text(detail.get("source_attribution") or {}),
            _json_text(detail.get("repair_plan") or {}),
            _df(detail.get("one_shot_trace_rows") or [], TRACE_COLUMNS),
            _df(detail.get("repaired_trace_rows") or [], TRACE_COLUMNS),
        )
    except Exception as error:
        return (
            f"Load failed: {error}",
            "{}",
            "{}",
            "{}",
            "{}",
            _df([], TRACE_COLUMNS),
            _df([], TRACE_COLUMNS),
        )


def _safe_summaries(
    output_root: Path,
    dataset_configs: tuple[DashboardDatasetConfig, ...],
) -> list[dict[str, Any]]:
    try:
        return load_all_dataset_summaries(output_root, dataset_configs)
    except Exception:
        return []


def _initial_seed(summaries: list[dict[str, Any]], dataset_label: str) -> int | None:
    if not dataset_label:
        return None
    try:
        seeds = seed_choices(find_summary_by_label(dataset_label, summaries))
    except ValueError:
        return None
    return seeds[0] if seeds else None


def _seed_choices_for_label(summaries: list[dict[str, Any]], dataset_label: str) -> list[int]:
    if not dataset_label:
        return []
    try:
        return seed_choices(find_summary_by_label(dataset_label, summaries))
    except ValueError:
        return []


def _empty_seed_outputs():
    return (
        "No seed selected.",
        "{}",
        "{}",
        "{}",
        "{}",
        _df([], TRACE_COLUMNS),
        _df([], TRACE_COLUMNS),
    )


def _status_text(detail: dict[str, Any]) -> str:
    if not detail:
        return "No seed selected."
    one_shot = _success_label(detail.get("one_shot_success"))
    repaired = _success_label(detail.get("repaired_success"))
    return (
        f"Seed `{detail.get('seed')}` | "
        f"one-shot: {one_shot}, reward `{detail.get('one_shot_reward')}`, "
        f"steps `{detail.get('one_shot_steps')}` | "
        f"repair: {repaired}, reward `{detail.get('repaired_reward')}`, "
        f"steps `{detail.get('repaired_steps')}`, status `{detail.get('repair_status')}`"
    )


def _success_label(value: Any) -> str:
    if value is None:
        return "n/a"
    return "success" if bool(value) else "failed"


def _json_text(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, indent=2)


def _df(rows: list[dict[str, Any]], columns: list[str]) -> pd.DataFrame:
    if pd is None:
        raise RuntimeError("Pandas is not installed. Install requirements.txt before launching.")
    return pd.DataFrame(rows, columns=columns)


def parse_args():
    parser = argparse.ArgumentParser(description="Open the Skill-GS JSON demo dashboard.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--skill-store", default=str(DEFAULT_SKILL_STORE_PATH))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7861)
    parser.add_argument(
        "--share",
        action="store_true",
        help="Create a temporary public Gradio link when localhost is blocked.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    build_app(args.output_root, args.skill_store).launch(
        server_name=args.host,
        server_port=args.port,
        share=args.share,
        show_error=True,
        show_api=False,
        enable_monitoring=False,
    )
