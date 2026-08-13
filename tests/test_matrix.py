from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from llm_gs.contracts import AblationMatrixSpecification
from llm_gs.matrix import build_matrix_manifests, matrix_report


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("OPENAI_API_KEY", None)
    return subprocess.run(
        ["llm-gs", *args], check=False, capture_output=True, text=True, env=environment
    )


def test_complete_frozen_ablation_matrix_is_paired_and_reports_all_arms() -> None:
    specification = AblationMatrixSpecification.model_validate(
        {
            "display_name": "complete-ablation",
            "seed_suite": {"memory_training": [1], "development": [2], "held_out": [3]},
            "search_seed": 7,
            "replicates": [2, 3],
        }
    )

    manifests = build_matrix_manifests(specification)

    assert len(manifests) == 96
    assert {manifest.task["name"] for manifest in manifests} == {
        "CleanHouse",
        "FourCorners",
        "DoorKey",
        "RedBlueDoor",
    }
    assert {manifest.search_strategy["name"] for manifest in manifests} == {
        "single_candidate",
        "cem",
        "cebs",
    }
    assert {manifest.failure_strategy["name"] for manifest in manifests} == {
        "regenerate",
        "reflect",
        "memory_repair",
        "memory_reflect",
    }
    for task_name in {manifest.task["name"] for manifest in manifests}:
        task_manifests = [manifest for manifest in manifests if manifest.task["name"] == task_name]
        assert len({frozenset(manifest.budgets.items()) for manifest in task_manifests}) == 1
        assert len({frozenset(manifest.model.items()) for manifest in task_manifests}) == 1
        assert len(
            {
                json.dumps(manifest.specification["seed_suite"], sort_keys=True)
                for manifest in task_manifests
            }
        ) == 1

    report = matrix_report(
        [
            {
                "experiment_id": f"exp_{index}",
                "protocol": "Frozen",
                "fixed_budget_success_rate": 1.0 if index % 2 else 0.0,
                "missingness": {"incomplete_executions": 0},
                "failure_classes": {"infrastructure": 0, "model_output": 0, "replacements": 0},
            }
            for index in range(48)
        ]
    )
    assert report["arms"] == 48
    assert len(report["arm_reports"]) == 48
    assert report["protocols"]["Frozen"]["arms"] == 48
    assert report["protocols"]["Online"]["arms"] == 0
    assert report["missingness"] == {"incomplete_executions": 0, "unreported_arms": 0}
    assert report["failure_classes"] == {
        "infrastructure": 0,
        "model_output": 0,
        "replacements": 0,
    }
    assert report["protocols"]["Frozen"]["confidence_interval"]["method"] == "wilson-95"


def test_matrix_cli_validates_and_reports_unrun_arms_without_omitting_them(tmp_path: Path) -> None:
    specification = tmp_path / "matrix.yaml"
    workspace = tmp_path / "workspace"
    specification.write_text(
        """\
matrix_version: 1
display_name: complete-ablation
seed_suite:
  version: 1
  memory_training: [1]
  development: [2]
  held_out: [3]
search_seed: 7
replicates: [2]
max_repair_cycles: 1
""",
        encoding="utf-8",
    )

    validation = _run_cli("matrix", "validate", str(specification))
    report = _run_cli("matrix", "report", str(specification), "--workspace", str(workspace))

    assert validation.returncode == 0, validation.stderr
    assert len(json.loads(validation.stdout)["arms"]) == 48
    assert report.returncode == 0, report.stderr
    matrix = json.loads(report.stdout)
    assert matrix["arms"] == 48
    assert len(matrix["arm_reports"]) == 48
    assert matrix["exclusions"] == {"count": 0, "arms": []}
    assert matrix["missingness"] == {"incomplete_executions": 0, "unreported_arms": 48}
    assert matrix["protocols"]["Frozen"]["arms"] == 0
    assert matrix["protocols"]["Frozen"]["fixed_budget_success_rate"] is None
    assert matrix["protocols"]["Online"]["arms"] == 0
    assert matrix["protocols"]["Online"]["fixed_budget_success_rate"] is None
    assert matrix["protocols"]["Frozen"]["confidence_interval"]["method"] == "wilson-95"


def test_matrix_cli_runs_the_complete_cross_product_with_fake_model(tmp_path: Path) -> None:
    specification = tmp_path / "matrix.yaml"
    workspace = tmp_path / "workspace"
    specification.write_text(
        """\
matrix_version: 1
display_name: complete-ablation-run
seed_suite:
  version: 1
  memory_training: [1]
  development: [2]
  held_out: [3]
max_repair_cycles: 1
""",
        encoding="utf-8",
    )

    run = _run_cli("matrix", "run", str(specification), "--workspace", str(workspace))

    assert run.returncode == 0, run.stderr
    matrix = json.loads(run.stdout)
    assert matrix["arms"] == 48
    assert len(matrix["arm_reports"]) == 48
    assert matrix["protocols"]["Frozen"]["arms"] == 48
    assert matrix["protocols"]["Online"]["arms"] == 0
    assert matrix["missingness"] == {"incomplete_executions": 0, "unreported_arms": 0}
