from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import httpx
import pytest
from openai import APIStatusError

from llm_gs import cli
from llm_gs.contracts import AblationMatrixSpecification, CandidateProgram
from llm_gs.execution import FakeOpenAIClient
from llm_gs.matrix import build_matrix_manifests, matrix_report
from llm_gs.proposer import CostBudget, ModelOutputFailure, OpenAIProposer


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
        assert len({frozenset(manifest.model.items()) for manifest in task_manifests}) == 1
        assert len(
            {
                json.dumps(manifest.specification["seed_suite"], sort_keys=True)
                for manifest in task_manifests
            }
        ) == 1
        for strategy_name in {manifest.search_strategy["name"] for manifest in task_manifests}:
            strategy_manifests = [
                manifest
                for manifest in task_manifests
                if manifest.search_strategy["name"] == strategy_name
            ]
            budgets = {frozenset(manifest.budgets.items()) for manifest in strategy_manifests}
            assert len(budgets) == 1
        single_candidate_budget = next(
            manifest.budgets["episode_evaluations"]
            for manifest in task_manifests
            if manifest.search_strategy["name"] == "single_candidate"
        )
        for manifest in task_manifests:
            if manifest.search_strategy["name"] != "single_candidate":
                assert manifest.budgets["episode_evaluations"] > single_candidate_budget

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
        "development-gated": 0,
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
    assert matrix["protocols"]["Frozen"]["arms"] == 0
    assert matrix["protocols"]["Online"]["arms"] == 0
    assert matrix["missingness"] == {"incomplete_executions": 0, "unreported_arms": 0}
    assert matrix["arm_states"] == {
        "pending": 0,
        "running": 0,
        "completed": 0,
        "development-gated": 48,
        "model-output-failed": 0,
        "infrastructure-failed": 0,
        "blocked-by-budget": 0,
    }
    assert matrix["development_gated"] == {
        "count": 48,
        "reasons": {"development_admission_failed": 48},
    }
    persisted_report = workspace / "matrix-report.json"
    on_demand_report = _run_cli(
        "matrix", "report", str(specification), "--workspace", str(workspace)
    )
    assert persisted_report.read_text(encoding="utf-8") == run.stdout
    assert on_demand_report.returncode == 0, on_demand_report.stderr
    assert persisted_report.read_text(encoding="utf-8") == on_demand_report.stdout

    progress_lines = [line for line in run.stderr.splitlines() if line]
    running_lines = [line for line in progress_lines if "-> running" in line]
    gated_lines = [line for line in progress_lines if "-> development-gated" in line]
    assert len(running_lines) == 48
    assert len(gated_lines) == 48
    for index, (running_line, gated_line) in enumerate(
        zip(running_lines, gated_lines, strict=True), start=1
    ):
        assert running_line.startswith(f"[{index}/48] ")
        assert running_line.endswith("-> running (attempt 1/3)")
        assert gated_line.startswith(f"[{index}/48] ")
        assert gated_line.endswith("-> development-gated")


def test_matrix_cli_rejects_unknown_model_without_prices_before_workspace_write(
    tmp_path: Path,
) -> None:
    specification = tmp_path / "matrix.yaml"
    workspace = tmp_path / "workspace"
    specification.write_text(
        """\
matrix_version: 1
display_name: missing-model-prices
seed_suite:
  version: 1
  memory_training: [1]
  development: [2]
  held_out: [3]
max_repair_cycles: 1
""",
        encoding="utf-8",
    )

    result = _run_cli(
        "matrix",
        "run",
        str(specification),
        "--workspace",
        str(workspace),
        "--enable-live-openai",
        "--max-cost-usd",
        "1",
        "--model",
        "test-model",
    )

    assert result.returncode == 2
    assert "unknown model requires all three" in result.stderr
    assert not workspace.exists()


def test_unknown_model_with_all_prices_builds_a_live_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = cli._parser().parse_args(
        [
            "matrix",
            "run",
            str(tmp_path / "matrix.yaml"),
            "--workspace",
            str(tmp_path / "workspace"),
            "--enable-live-openai",
            "--max-cost-usd",
            "1",
            "--model",
            "test-model",
            "--input-price-usd-per-million-token",
            "1",
            "--cached-input-price-usd-per-million-token",
            "0",
            "--output-price-usd-per-million-token",
            "2",
        ]
    )

    captured: dict[str, object] = {}

    def build_client(**kwargs: object) -> FakeOpenAIClient:
        captured.update(kwargs)
        return FakeOpenAIClient()

    monkeypatch.setattr(cli, "OpenAIProposer", build_client)

    client = cli._model_client(args)

    assert isinstance(client, FakeOpenAIClient)
    assert captured["model_name"] == "test-model"
    pricing = captured["pricing"]
    assert pricing is not None
    assert pricing.input_usd_per_token == 0.000_001
    assert pricing.cached_input_usd_per_token == 0
    assert pricing.output_usd_per_token == 0.000_002


def test_matrix_pricing_catalog_persists_new_models_and_partial_updates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog_path = tmp_path / "model-pricing.yaml"
    catalog_path.write_text(
        """\
models:
  existing-model:
    input_usd_per_million_token: 1
    cached_input_usd_per_million_token: 0
    output_usd_per_million_token: 2
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "MODEL_PRICING_CATALOG_PATH", catalog_path)

    new_model = cli._parser().parse_args(
        [
            "matrix", "run", str(tmp_path / "matrix.yaml"), "--workspace",
            str(tmp_path / "workspace"),
            "--enable-live-openai", "--max-cost-usd", "1", "--model", "new-model",
            "--input-price-usd-per-million-token", "3",
            "--cached-input-price-usd-per-million-token", "0",
            "--output-price-usd-per-million-token", "4",
        ]
    )
    assert cli._matrix_pricing_from_args(new_model).output_usd_per_token == 0.000_004

    remembered = cli._parser().parse_args(
        [
            "matrix", "run", str(tmp_path / "matrix.yaml"), "--workspace",
            str(tmp_path / "workspace"),
            "--enable-live-openai", "--max-cost-usd", "1", "--model", "new-model",
        ]
    )
    assert cli._matrix_pricing_from_args(remembered).input_usd_per_token == 0.000_003

    update = cli._parser().parse_args(
        [
            "matrix", "run", str(tmp_path / "matrix.yaml"), "--workspace",
            str(tmp_path / "workspace"),
            "--enable-live-openai", "--max-cost-usd", "1", "--model", "existing-model",
            "--output-price-usd-per-million-token", "5",
        ]
    )
    pricing = cli._matrix_pricing_from_args(update)
    assert pricing.input_usd_per_token == 0.000_001
    assert pricing.cached_input_usd_per_token == 0
    assert pricing.output_usd_per_token == 0.000_005
    assert cli._load_model_pricing_catalog(catalog_path)["existing-model"] == pricing


def test_matrix_pricing_catalog_rejects_invalid_or_incomplete_entries_before_workspace_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog_path = tmp_path / "model-pricing.yaml"
    catalog_path.write_text("models:\n  broken: [1, 2, 3]\n", encoding="utf-8")
    monkeypatch.setattr(cli, "MODEL_PRICING_CATALOG_PATH", catalog_path)
    args = cli._parser().parse_args(
        [
            "matrix", "run", str(tmp_path / "matrix.yaml"), "--workspace",
            str(tmp_path / "workspace"),
            "--enable-live-openai", "--max-cost-usd", "1",
        ]
    )
    with pytest.raises(ValueError, match="invalid model pricing catalog"):
        cli._matrix_pricing_from_args(args)
    assert not (tmp_path / "workspace").exists()

    catalog_path.write_text("models: {}\n", encoding="utf-8")
    incomplete = cli._parser().parse_args(
        [
            "matrix", "run", str(tmp_path / "matrix.yaml"), "--workspace",
            str(tmp_path / "workspace"),
            "--enable-live-openai", "--max-cost-usd", "1", "--model", "new-model",
            "--input-price-usd-per-million-token", "1",
        ]
    )
    with pytest.raises(ValueError, match="unknown model requires all three"):
        cli._matrix_pricing_from_args(incomplete)
    assert not (tmp_path / "workspace").exists()


def test_matrix_pricing_is_saved_before_model_client_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    specification = tmp_path / "matrix.yaml"
    specification.write_text(
        """\
matrix_version: 1
display_name: priced-before-execution
seed_suite:
  version: 1
  memory_training: [1]
  development: [2]
  held_out: [3]
max_repair_cycles: 1
""",
        encoding="utf-8",
    )
    catalog_path = tmp_path / "model-pricing.yaml"
    catalog_path.write_text("models: {}\n", encoding="utf-8")
    monkeypatch.setattr(cli, "MODEL_PRICING_CATALOG_PATH", catalog_path)
    monkeypatch.setattr(
        cli, "_model_client", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline"))
    )
    workspace = tmp_path / "workspace"
    args = cli._parser().parse_args(
        [
            "matrix", "run", str(specification), "--workspace", str(workspace),
            "--enable-live-openai", "--max-cost-usd", "1", "--model", "new-model",
            "--input-price-usd-per-million-token", "1",
            "--cached-input-price-usd-per-million-token", "0",
            "--output-price-usd-per-million-token", "2",
        ]
    )

    with pytest.raises(RuntimeError, match="offline"):
        args.handler(args)

    assert "new-model" in cli._load_model_pricing_catalog(catalog_path)
    assert not workspace.exists()


@pytest.mark.parametrize("status_code", [400, 403, 404])
def test_model_configuration_status_error_is_not_retriable(
    monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    error = APIStatusError(
        "model request rejected",
        response=httpx.Response(
            status_code, request=httpx.Request("POST", "https://api.openai.com/v1/responses")
        ),
        body=None,
    )
    store = mock.Mock()
    monkeypatch.setattr(
        cli,
        "execute_resumable",
        lambda *args, **kwargs: (_ for _ in ()).throw(error),
    )

    with pytest.raises(cli.ModelConfigurationError, match="model configuration error"):
        cli._execute_with_failure_recording(
            SimpleNamespace(task={"name": "CleanHouse"}),
            "experiment",
            store,
            SimpleNamespace(),
            model=FakeOpenAIClient(),
        )

    store.record_execution_failure.assert_called_once()


def test_matrix_stops_after_model_configuration_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    specification = tmp_path / "matrix.yaml"
    workspace = tmp_path / "workspace"
    specification.write_text(
        """\
matrix_version: 1
display_name: model-configuration-error
seed_suite:
  memory_training: [1]
  development: [2]
  held_out: [3]
max_repair_cycles: 1
""",
        encoding="utf-8",
    )
    calls = 0

    def execute(*args: object, **kwargs: object) -> tuple[None, str]:
        nonlocal calls
        calls += 1
        raise cli.ModelConfigurationError("model configuration error: rejected")

    monkeypatch.setattr(cli, "_execute_with_failure_recording", execute)
    args = cli._parser().parse_args(
        ["matrix", "run", str(specification), "--workspace", str(workspace)]
    )

    with pytest.raises(cli.ModelConfigurationError, match="model configuration error"):
        args.handler(args)

    assert calls == 1
    assert not (workspace / "matrix-report.json").exists()


def test_live_matrix_uses_one_shared_cost_budget_and_reports_reconciliation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    specification = tmp_path / "matrix.yaml"
    workspace = tmp_path / "workspace"
    specification.write_text(
        """\
matrix_version: 1
display_name: priced-matrix
seed_suite:
  memory_training: [1]
  development: [2]
  held_out: [3]
max_repair_cycles: 1
""",
        encoding="utf-8",
    )

    class Responses:
        def create(self, **kwargs: object) -> object:
            prompt = str(kwargs["input"])
            source = (
                "DEF run m( left m)"
                if "DoorKey" in prompt or "RedBlueDoor" in prompt
                else "DEF run m( turnLeft m)"
            )
            return SimpleNamespace(
                output_text=json.dumps({"source": source}),
                usage=SimpleNamespace(
                    input_tokens=10,
                    output_tokens=5,
                    input_tokens_details=SimpleNamespace(cached_tokens=2),
                ),
                status="completed",
            )

    budgets: list[CostBudget] = []

    def model_client(
        args: object, total_cost_budget: CostBudget | None = None, pricing: object = None
    ) -> OpenAIProposer:
        assert total_cost_budget is not None
        assert pricing is not None
        budgets.append(total_cost_budget)
        return OpenAIProposer(
            Responses(), total_cost_budget=total_cost_budget, max_cost_usd=1, pricing=pricing
        )

    monkeypatch.setattr(cli, "_model_client", model_client)
    catalog = tmp_path / "model-pricing.yaml"
    catalog.write_text("models: {}\n", encoding="utf-8")
    monkeypatch.setattr(cli, "MODEL_PRICING_CATALOG_PATH", catalog)
    args = cli._parser().parse_args(
        [
            "matrix", "run", str(specification), "--workspace", str(workspace),
            "--enable-live-openai", "--max-cost-usd", "1", "--max-total-cost-usd", "7",
            "--model", "test-model",
            "--input-price-usd-per-million-token", "0.2",
            "--cached-input-price-usd-per-million-token", "0.2",
            "--output-price-usd-per-million-token", "1.2",
        ]
    )

    assert args.model == "test-model"
    matrix = args.handler(args)

    assert len(budgets) == 1
    assert len({id(budget) for budget in budgets}) == 1
    assert matrix["arm_states"]["development-gated"] == 48
    assert matrix["protocols"]["Frozen"]["arms"] == 0
    cost = matrix["cost"]
    assert cost["cap_usd"] == 7.0
    assert cost["reserved_usd"] == 0.0
    assert cost["unknown_usd"] == 0.0
    assert cost["settled_usd"] == pytest.approx(cost["input_tokens"] / 10 * 0.000_008)
    assert cost["remaining_usd"] == pytest.approx(7 - cost["settled_usd"])
    assert cost["cached_tokens"] == cost["input_tokens"] / 5
    assert cost["output_tokens"] == cost["input_tokens"] / 2
    assert cost["pricing"] == {
        "model": "test-model",
        "input_usd_per_million_token": 0.2,
        "cached_input_usd_per_million_token": 0.2,
        "output_usd_per_million_token": 1.2,
    }
    arm_settled = sum(arm["cost"]["settled_usd"] for arm in matrix["arm_reports"])
    assert arm_settled == pytest.approx(cost["settled_usd"])

    report_args = cli._parser().parse_args(
        ["matrix", "report", str(specification), "--workspace", str(workspace)]
    )
    assert report_args.handler(report_args)["cost"] == cost


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
        (
            ModelOutputFailure("model request exceeds the configured cost cap"),
            "blocked-by-budget",
            "budget",
        ),
        (TimeoutError("network unavailable"), "infrastructure-failed", "infrastructure"),
        (RuntimeError("evaluator crashed"), "infrastructure-failed", "infrastructure"),
        (Exception("unexpected runner failure"), "infrastructure-failed", "infrastructure"),
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
        def propose(self, prompt: str) -> CandidateProgram:
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
        "development-gated": 0,
        "model-output-failed": 48 if expected_state == "model-output-failed" else 0,
        "infrastructure-failed": 48 if expected_state == "infrastructure-failed" else 0,
        "blocked-by-budget": 48 if expected_state == "blocked-by-budget" else 0,
    }
    aggregate_class = (
        "infrastructure" if expected_error_class == "execution" else expected_error_class
    )
    expected_failures = 144 if expected_state == "infrastructure-failed" else 48
    assert matrix["failure_classes"][aggregate_class] == expected_failures
    assert all(
        arm["arm_error"]["class"] == expected_error_class for arm in matrix["arm_reports"]
    )
    assert all(
        str(failure) in arm["arm_error"]["detail"]
        for arm in matrix["arm_reports"]
    )
    assert (workspace / "matrix-report.json").read_text(encoding="utf-8") == (
        cli._json_output(matrix) + "\n"
    )


def test_matrix_run_reports_output_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    failure = OSError("disk full")
    monkeypatch.setattr(Path, "replace", lambda *args: (_ for _ in ()).throw(failure))

    with pytest.raises(
        ValueError, match="could not write Matrix Report to .*matrix-report.json: disk full"
    ):
        cli._write_matrix_report(workspace, {"arms": 0})

    assert not list(workspace.glob(".matrix-report.*.tmp"))


def test_matrix_run_retries_infrastructure_with_new_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    specification = tmp_path / "matrix.yaml"
    workspace = tmp_path / "workspace"
    specification.write_text(
        """\
matrix_version: 1
display_name: resumable
seed_suite:
  memory_training: [1]
  development: [2]
  held_out: [3]
max_repair_cycles: 1
""",
        encoding="utf-8",
    )
    manifest = build_matrix_manifests(
        AblationMatrixSpecification.model_validate(
            {
                "display_name": "resumable",
                "seed_suite": {
                    "memory_training": [1],
                    "development": [2],
                    "held_out": [3],
                },
            }
        )
    )[0]
    monkeypatch.setattr(cli, "build_matrix_manifests", lambda _: (manifest,))
    attempts = 0

    def execute(*args: object, **kwargs: object) -> tuple[object, str]:
        nonlocal attempts
        attempts += 1
        store = args[2]
        assert hasattr(store, "next_execution_id")
        experiment = args[1]
        execution_id = store.next_execution_id(experiment)
        store.begin_execution_for_experiment(
            manifest, experiment, execution_id, "DEF run m( move m)", 1
        )
        if attempts <= 3:
            store.record_execution_failure(experiment, execution_id, "infrastructure", "transient")
            raise ValueError("infrastructure failure: transient")
        from llm_gs.contracts import ExperimentReport

        report = ExperimentReport(
            experiment_id=experiment,
            execution_id=execution_id,
            candidate_programs=1,
            episode_evaluations=1,
            model_requests=1,
            outcomes={"success": 1},
        )
        store.save(manifest, report)
        return report, "completed"

    monkeypatch.setattr(cli, "_execute_with_failure_recording", execute)
    args = cli._parser().parse_args(
        ["matrix", "run", str(specification), "--workspace", str(workspace)]
    )

    first_matrix = args.handler(args)
    first_run_progress = [
        line for line in capsys.readouterr().err.splitlines() if line
    ]

    first_arm = first_matrix["arm_reports"][0]
    assert first_arm["arm_state"] == "infrastructure-failed"
    assert len(first_arm["executions"]) == 3
    assert first_arm["failure_classes"]["replacements"] == 2
    assert first_run_progress == [
        "[1/1] " + first_arm["experiment_id"] + " -> running (attempt 1/3)",
        "[1/1] " + first_arm["experiment_id"] + " -> running (attempt 2/3)",
        "[1/1] " + first_arm["experiment_id"] + " -> running (attempt 3/3)",
        "[1/1] " + first_arm["experiment_id"] + " -> infrastructure-failed",
    ]

    matrix = args.handler(args)

    assert attempts == 4
    arm = matrix["arm_reports"][0]
    assert arm["arm_state"] == "completed"
    assert len(arm["executions"]) == 4
    assert arm["missingness"] == {"incomplete_executions": 0}
    assert arm["failure_classes"]["infrastructure"] == 3
    assert arm["failure_classes"]["replacements"] == 3


def test_matrix_run_recovers_with_fake_client_without_erasing_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    specification = tmp_path / "matrix.yaml"
    workspace = tmp_path / "workspace"
    specification.write_text(
        """\
matrix_version: 1
display_name: fake-client-resume
seed_suite:
  memory_training: [1]
  development: [2]
  held_out: [3]
max_repair_cycles: 1
""",
        encoding="utf-8",
    )
    manifest = build_matrix_manifests(
        AblationMatrixSpecification.model_validate(
            {
                "display_name": "fake-client-resume",
                "seed_suite": {
                    "memory_training": [1],
                    "development": [2],
                    "held_out": [3],
                },
            }
        )
    )[0]
    monkeypatch.setattr(cli, "build_matrix_manifests", lambda _: (manifest,))

    class FlakyClient(FakeOpenAIClient):
        attempts = 0
        transport_failures = 0

        def propose(self, prompt: str) -> CandidateProgram:
            self.attempts += 1
            if self.attempts <= 3:
                self.transport_failures += 1
                raise OSError("temporary model transport outage")
            return super().propose(prompt)

    client = FlakyClient()
    monkeypatch.setattr(cli, "_model_client", lambda *args, **kwargs: client)
    args = cli._parser().parse_args(
        ["matrix", "run", str(specification), "--workspace", str(workspace)]
    )

    failed = args.handler(args)["arm_reports"][0]
    recovered = args.handler(args)
    arm = recovered["arm_reports"][0]

    assert client.transport_failures == 3
    assert failed["arm_state"] == "infrastructure-failed"
    assert [execution["status"] for execution in arm["executions"]] == [
        "failed",
        "failed",
        "failed",
        "completed",
    ]
    assert arm["failure_classes"] == {
        "budget": 0,
        "infrastructure": 3,
        "model_output": 0,
        "replacements": 3,
    }
    assert arm["arm_state"] == "development-gated"
    assert recovered["protocols"]["Frozen"]["arms"] == 0
    assert recovered["protocols"]["Online"]["arms"] == 0


def test_matrix_run_does_not_retry_model_output_as_infrastructure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    specification = tmp_path / "matrix.yaml"
    workspace = tmp_path / "workspace"
    specification.write_text(
        """\
matrix_version: 1
display_name: model-output-no-retry
seed_suite:
  memory_training: [1]
  development: [2]
  held_out: [3]
max_repair_cycles: 1
""",
        encoding="utf-8",
    )
    manifest = build_matrix_manifests(
        AblationMatrixSpecification.model_validate(
            {
                "display_name": "model-output-no-retry",
                "seed_suite": {
                    "memory_training": [1],
                    "development": [2],
                    "held_out": [3],
                },
            }
        )
    )[0]
    monkeypatch.setattr(cli, "build_matrix_manifests", lambda _: (manifest,))

    class InvalidClient(FakeOpenAIClient):
        attempts = 0

        def propose(self, prompt: str) -> object:
            self.attempts += 1
            raise ModelOutputFailure("invalid schema")

    client = InvalidClient()
    monkeypatch.setattr(cli, "_model_client", lambda *args, **kwargs: client)
    args = cli._parser().parse_args(
        ["matrix", "run", str(specification), "--workspace", str(workspace)]
    )

    arm = args.handler(args)["arm_reports"][0]
    progress = [line for line in capsys.readouterr().err.splitlines() if line]

    assert client.attempts == 1
    assert arm["arm_state"] == "model-output-failed"
    assert progress == [
        "[1/1] " + arm["experiment_id"] + " -> running (attempt 1/3)",
        "[1/1] " + arm["experiment_id"] + " -> model-output-failed",
    ]
    assert arm["arm_error"] == {
        "class": "model_output",
        "detail": "model output failure: invalid schema",
    }
    assert arm["failure_classes"] == {
        "budget": 0,
        "infrastructure": 0,
        "model_output": 1,
        "replacements": 0,
    }
    assert [execution["status"] for execution in arm["executions"]] == ["failed"]
