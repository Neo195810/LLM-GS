from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from llm_gs import cli
from llm_gs.contracts import AblationMatrixSpecification
from llm_gs.matrix import build_matrix_manifests, matrix_report
from llm_gs.proposer import ModelOutputFailure


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
                "failure_classes": {
                    "budget": 0,
                    "infrastructure": 0,
                    "model_output": 0,
                    "replacements": 0,
                },
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
        "budget": 0,
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
    assert matrix["missingness"] == {"incomplete_executions": 0, "unreported_arms": 0}
    assert matrix["arm_states"] == {
        "pending": 48,
        "running": 0,
        "completed": 0,
        "model-output-failed": 0,
        "infrastructure-failed": 0,
        "blocked-by-budget": 0,
    }
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
    assert matrix["arm_states"] == {
        "pending": 0,
        "running": 0,
        "completed": 48,
        "model-output-failed": 0,
        "infrastructure-failed": 0,
        "blocked-by-budget": 0,
    }


@pytest.mark.parametrize(
    ("failure", "expected_state", "expected_error_class"),
    [
        (
            ModelOutputFailure("model output failed schema or DSL validation"),
            "model-output-failed",
            "model_output",
        ),
        (
            ModelOutputFailure("model request exceeds the configured total cost cap"),
            "blocked-by-budget",
            "budget",
        ),
        (TimeoutError("network unavailable"), "infrastructure-failed", "infrastructure"),
        (RuntimeError("evaluator crashed"), "infrastructure-failed", "execution"),
    ],
)
def test_matrix_cli_persists_terminal_failure_state_for_every_arm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    expected_state: str,
    expected_error_class: str,
) -> None:
    specification = tmp_path / "matrix.yaml"
    workspace = tmp_path / "workspace"
    specification.write_text(
        """\
matrix_version: 1
display_name: model-output-failure
seed_suite:
  version: 1
  memory_training: [1]
  development: [2]
  held_out: [3]
max_repair_cycles: 1
""",
        encoding="utf-8",
    )

    class FailingModel:
        def propose(self, prompt: str) -> object:
            raise failure

        def repair(self, prompt: str) -> object:
            raise failure

    monkeypatch.setattr(cli, "_model_client", lambda *args, **kwargs: FailingModel())
    args = cli._parser().parse_args(
        ["matrix", "run", str(specification), "--workspace", str(workspace)]
    )

    matrix = args.handler(args)

    assert matrix["arms"] == 48
    assert matrix["missingness"] == {"incomplete_executions": 0, "unreported_arms": 0}
    assert matrix["arm_states"] == {
        "pending": 0,
        "running": 0,
        "completed": 0,
        "model-output-failed": 48 if expected_state == "model-output-failed" else 0,
        "infrastructure-failed": 48 if expected_state == "infrastructure-failed" else 0,
        "blocked-by-budget": 48 if expected_state == "blocked-by-budget" else 0,
    }
    aggregate_class = (
        "infrastructure" if expected_error_class == "execution" else expected_error_class
    )
    assert matrix["failure_classes"][aggregate_class] == 48
    assert all(
        arm["arm_error"]["class"] == expected_error_class for arm in matrix["arm_reports"]
    )
    assert all(
        str(failure) in arm["arm_error"]["detail"]
        for arm in matrix["arm_reports"]
    )
