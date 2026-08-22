from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape


COLORS = {
    "llm_generated": "#7c8da6",
    "llm_gs_style_search": "#d18b47",
    "ours_adaptive_skill_gs": "#2f8f83",
    "first_attempt": "#5d84c4",
    "repaired": "#2f8f83",
    "unrecovered": "#c84f4f",
}


def generate_evidence_pack(
    comparison: dict[str, Any],
    report_path: str | Path,
    assets_dir: str | Path,
) -> dict[str, Any]:
    """Write SVG charts and a Markdown demo summary for a comparison result."""

    report = Path(report_path)
    assets = Path(assets_dir)
    assets.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)

    table = comparison["comparison_table"]
    chart_paths = [
        _write_success_rate_chart(table, assets),
        _write_evaluation_count_chart(table, assets),
        _write_repair_breakdown_chart(comparison, assets),
    ]
    report.write_text(
        _render_report(comparison, report, chart_paths),
        encoding="utf-8",
    )
    return {
        "report_path": str(report),
        "assets_dir": str(assets),
        "charts": [str(path) for path in chart_paths],
    }


def _write_success_rate_chart(table: list[dict[str, Any]], assets: Path) -> Path:
    path = assets / "skill_gs_baseline_success_rate.svg"
    bars = [
        {
            "label": row["name"],
            "value": float(row["success_rate"]),
            "caption": f'{row["successes"]}/{row["num_runs"]}',
            "color": COLORS.get(row["name"], "#666666"),
        }
        for row in table
    ]
    path.write_text(
        _horizontal_bar_svg(
            title="Success Rate by Baseline",
            subtitle="Same DoorKey task, same seeds, same evaluator",
            bars=bars,
            value_suffix="",
            max_value=1.0,
            value_scale=100.0,
            value_format="{:.1f}%",
        ),
        encoding="utf-8",
    )
    return path


def _write_evaluation_count_chart(table: list[dict[str, Any]], assets: Path) -> Path:
    path = assets / "skill_gs_evaluation_count.svg"
    max_value = max(int(row["evaluation_count"]) for row in table)
    bars = [
        {
            "label": row["name"],
            "value": int(row["evaluation_count"]),
            "caption": f'max budget {row["max_execution_budget"]}',
            "color": COLORS.get(row["name"], "#666666"),
        }
        for row in table
    ]
    path.write_text(
        _horizontal_bar_svg(
            title="Evaluation Count",
            subtitle="Lower is better when success rate is tied",
            bars=bars,
            value_suffix=" evals",
            max_value=max_value,
            value_scale=1.0,
            value_format="{:.0f}",
        ),
        encoding="utf-8",
    )
    return path


def _write_repair_breakdown_chart(comparison: dict[str, Any], assets: Path) -> Path:
    path = assets / "skill_gs_adaptive_repair_breakdown.svg"
    ours = _row_by_name(comparison["comparison_table"], "ours_adaptive_skill_gs")
    memory = _group_by_name(comparison.get("groups", []), "ours_adaptive_skill_gs").get(
        "adaptive_memory",
        {},
    )
    successful_repairs = int(memory.get("successful_repairs", 0))
    successes = int(ours["successes"])
    num_runs = int(ours["num_runs"])
    first_attempt_successes = max(0, successes - successful_repairs)
    unrecovered = max(0, num_runs - successes)
    segments = [
        {
            "label": "first attempt success",
            "value": first_attempt_successes,
            "color": COLORS["first_attempt"],
        },
        {
            "label": "repaired by adaptive retry",
            "value": successful_repairs,
            "color": COLORS["repaired"],
        },
        {
            "label": "unrecovered",
            "value": unrecovered,
            "color": COLORS["unrecovered"],
        },
    ]
    path.write_text(
        _stacked_bar_svg(
            title="Adaptive Repair Breakdown",
            subtitle="How ours reaches final success",
            segments=segments,
            total=num_runs,
        ),
        encoding="utf-8",
    )
    return path


def _render_report(
    comparison: dict[str, Any],
    report_path: Path,
    chart_paths: list[Path],
) -> str:
    fairness = comparison.get("fairness", {})
    rows = comparison["comparison_table"]
    chart_links = [
        _markdown_image_path(report_path, chart_path)
        for chart_path in chart_paths
    ]
    ours = _row_by_name(rows, "ours_adaptive_skill_gs")
    search = _row_by_name(rows, "llm_gs_style_search")
    one_shot = _row_by_name(rows, "llm_generated")
    eval_saving = int(search["evaluation_count"]) - int(ours["evaluation_count"])

    return "\n".join(
        [
            "# Skill-GS Demo Evidence Pack",
            "",
            "日期：2026-08-22",
            "",
            "## 核心訊息",
            "",
            "這份 demo pack 將 Skill-GS 目前最重要的實驗結果整理成可展示版本：",
            "",
            "- `llm_generated` one-shot proxy：不做 search、不做 repair。",
            "- `llm_gs_style_search` proxy：用多個 candidate 做完整搜尋。",
            "- `ours_adaptive_skill_gs`：用 failure attribution、replanning、memory 與 retry budget schedule 做 adaptive repair。",
            "",
            "在 DoorKey seeds 0..127 的 local proxy comparison 中，ours 與 candidate search 都達到 128/128，但 ours 使用較少 evaluation 次數。",
            "",
            "## 實驗設定",
            "",
            "| Setting | Value |",
            "|---|---|",
            f"| Task | {comparison['task']} |",
            f"| Seeds | {_seed_label(fairness.get('seeds', []))} |",
            f"| Max allowed execution budget | {fairness.get('max_allowed_execution_budget')} |",
            f"| External LLM calls | {str(fairness.get('external_llm_calls')).lower()} |",
            "",
            "## 圖表",
            "",
            f"![Success Rate]({chart_links[0]})",
            "",
            f"![Evaluation Count]({chart_links[1]})",
            "",
            f"![Adaptive Repair Breakdown]({chart_links[2]})",
            "",
            "## 結果表",
            "",
            "| Group | Successes | Success Rate | Evaluation Count | Max Budget | Repair | Memory |",
            "|---|---:|---:|---:|---:|---|---|",
            *[_result_row(row) for row in rows],
            "",
            "## 解讀",
            "",
            f"- One-shot proxy 只成功 {one_shot['successes']}/{one_shot['num_runs']}，顯示低 budget 固定策略不足以穩定完成 DoorKey。",
            f"- LLM-GS-style search proxy 達到 {search['successes']}/{search['num_runs']}，但需要 {search['evaluation_count']} 次 evaluation。",
            f"- Ours 達到 {ours['successes']}/{ours['num_runs']}，只需要 {ours['evaluation_count']} 次 evaluation，比 search proxy 少 {eval_saving} 次。",
            "- 目前 failure attribution 指向 insufficient budget，而不是 not best skill。",
            "",
            "## Demo 指令",
            "",
            "```powershell",
            "python scripts\\skill_gs\\run_baseline_comparison.py --seed-start 0 --seed-end 127 --initial-max-steps 10 --search-candidate-max-steps 10 20 22 24 --ours-retry-budget-schedule 20 22 24 --ours-max-attempts 4 --perturbation-seed 123 --output output\\skill_gs\\baseline_comparison_seed0_127.json",
            "python scripts\\skill_gs\\generate_evidence_pack.py --baseline-json output\\skill_gs\\baseline_comparison_seed0_127.json",
            "```",
            "",
            "## 限制",
            "",
            "這裡的 LLM-named baselines 是 reproducible local proxy，尚未接真正外部 LLM API。這讓展示更穩定，但不能直接宣稱已完整重現 paper 的 LLM-GS 搜尋結果。",
            "",
        ]
    )


def _horizontal_bar_svg(
    title: str,
    subtitle: str,
    bars: list[dict[str, Any]],
    value_suffix: str,
    max_value: float,
    value_scale: float,
    value_format: str,
) -> str:
    width = 900
    height = 150 + len(bars) * 78
    label_x = 42
    bar_x = 300
    bar_width = 500
    bar_height = 32
    rows = []
    for index, bar in enumerate(bars):
        y = 104 + index * 78
        value = float(bar["value"])
        scaled_width = 0 if max_value <= 0 else (value / max_value) * bar_width
        display_value = value_format.format(value * value_scale)
        rows.append(
            "\n".join(
                [
                    f'<text x="{label_x}" y="{y + 22}" class="label">{escape(str(bar["label"]))}</text>',
                    f'<rect x="{bar_x}" y="{y}" width="{bar_width}" height="{bar_height}" rx="6" class="track" />',
                    f'<rect x="{bar_x}" y="{y}" width="{scaled_width:.2f}" height="{bar_height}" rx="6" fill="{bar["color"]}" />',
                    f'<text x="{bar_x + bar_width + 18}" y="{y + 22}" class="value">{escape(display_value + value_suffix)}</text>',
                    f'<text x="{bar_x}" y="{y + 56}" class="caption">{escape(str(bar["caption"]))}</text>',
                ]
            )
        )
    return _svg_document(width, height, title, subtitle, "\n".join(rows))


def _stacked_bar_svg(
    title: str,
    subtitle: str,
    segments: list[dict[str, Any]],
    total: int,
) -> str:
    width = 900
    height = 330
    bar_x = 72
    bar_y = 120
    bar_width = 756
    bar_height = 54
    cursor = bar_x
    parts = []
    for segment in segments:
        value = int(segment["value"])
        segment_width = 0 if total <= 0 else (value / total) * bar_width
        if segment_width > 0:
            parts.append(
                f'<rect x="{cursor:.2f}" y="{bar_y}" width="{segment_width:.2f}" height="{bar_height}" fill="{segment["color"]}" />'
            )
        cursor += segment_width
    legend = []
    for index, segment in enumerate(segments):
        x = 80 + index * 250
        y = 226
        value = int(segment["value"])
        percent = 0.0 if total <= 0 else value / total * 100
        legend.append(
            "\n".join(
                [
                    f'<rect x="{x}" y="{y}" width="16" height="16" fill="{segment["color"]}" />',
                    f'<text x="{x + 24}" y="{y + 13}" class="label">{escape(str(segment["label"]))}</text>',
                    f'<text x="{x + 24}" y="{y + 39}" class="caption">{value}/{total} ({percent:.1f}%)</text>',
                ]
            )
        )
    body = "\n".join(
        [
            f'<rect x="{bar_x}" y="{bar_y}" width="{bar_width}" height="{bar_height}" rx="8" class="track" />',
            *parts,
            *legend,
        ]
    )
    return _svg_document(width, height, title, subtitle, body)


def _svg_document(
    width: int,
    height: int,
    title: str,
    subtitle: str,
    body: str,
) -> str:
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            "<style>",
            "text { font-family: Arial, Helvetica, sans-serif; fill: #1f2933; }",
            ".title { font-size: 28px; font-weight: 700; }",
            ".subtitle { font-size: 15px; fill: #64748b; }",
            ".label { font-size: 15px; font-weight: 600; }",
            ".value { font-size: 15px; font-weight: 700; }",
            ".caption { font-size: 13px; fill: #64748b; }",
            ".track { fill: #e8edf3; }",
            "</style>",
            '<rect width="100%" height="100%" fill="#fbfcfe" />',
            f'<text x="42" y="46" class="title">{escape(title)}</text>',
            f'<text x="42" y="72" class="subtitle">{escape(subtitle)}</text>',
            body,
            "</svg>",
        ]
    )


def _result_row(row: dict[str, Any]) -> str:
    return (
        f"| `{row['name']}` | {row['successes']}/{row['num_runs']} | "
        f"{float(row['success_rate']):.6f} | {row['evaluation_count']} | "
        f"{row['max_execution_budget']} | {_yes_no(row['repair_enabled'])} | "
        f"{_yes_no(row['memory_enabled'])} |"
    )


def _markdown_image_path(report_path: Path, chart_path: Path) -> str:
    try:
        return chart_path.relative_to(report_path.parent).as_posix()
    except ValueError:
        return chart_path.as_posix()


def _row_by_name(rows: list[dict[str, Any]], name: str) -> dict[str, Any]:
    for row in rows:
        if row["name"] == name:
            return row
    raise KeyError(f"Missing comparison row: {name}")


def _group_by_name(groups: list[dict[str, Any]], name: str) -> dict[str, Any]:
    for group in groups:
        if group["name"] == name:
            return group
    return {}


def _seed_label(seeds: list[int]) -> str:
    if not seeds:
        return "none"
    if seeds == list(range(seeds[0], seeds[-1] + 1)):
        return f"{seeds[0]}..{seeds[-1]}"
    return ", ".join(str(seed) for seed in seeds)


def _yes_no(value: Any) -> str:
    return "yes" if value else "no"
