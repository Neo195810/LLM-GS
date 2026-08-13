from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("OPENAI_API_KEY", None)
    return subprocess.run(
        ["llm-gs", *args],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def write_specification(path: Path) -> None:
    path.write_text(
        """\
spec_version: 1
display_name: offline-smoke
task:
  name: offline.echo
seeds:
  task: [7]
""",
        encoding="utf-8",
    )


def test_valid_specification_runs_offline_through_a_deterministic_report(
    tmp_path: Path,
) -> None:
    specification = tmp_path / "experiment.yaml"
    workspace = tmp_path / "workspace"
    write_specification(specification)

    first_validation = run_cli("validate", str(specification))
    second_validation = run_cli("validate", str(specification))

    assert first_validation.returncode == 0, first_validation.stderr
    assert first_validation.stdout == second_validation.stdout
    validation = json.loads(first_validation.stdout)
    assert validation["experiment_id"].startswith("exp_")
    assert validation["manifest"]["model"] == {
        "client": "fake",
        "max_output_tokens": 1024,
        "model": "fake-openai-v1",
        "reasoning_effort": "medium",
    }
    assert validation["manifest"]["budgets"] == {
        "episode_evaluations": 1,
        "input_tokens": 4096,
        "model_requests": 1,
        "output_tokens": 1024,
    }
    assert validation["manifest"]["failure_strategy"] == {
        "max_repair_cycles": 3,
        "name": "regenerate",
    }
    assert validation["manifest"]["code"]["source_sha256"].startswith("sha256:")
    assert validation["manifest"]["dependencies"]["uv_lock_sha256"].startswith("sha256:")

    run = run_cli("run", str(specification), "--workspace", str(workspace))
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout) == {
        "execution_id": "exec_000001",
        "experiment_id": validation["experiment_id"],
        "status": "completed",
    }

    first_report = run_cli(
        "report",
        "--workspace",
        str(workspace),
        "--experiment-id",
        validation["experiment_id"],
    )
    second_report = run_cli(
        "report",
        "--workspace",
        str(workspace),
        "--experiment-id",
        validation["experiment_id"],
    )

    assert first_report.returncode == 0, first_report.stderr
    assert first_report.stdout == second_report.stdout
    report = json.loads(first_report.stdout)
    assert {key: report[key] for key in (
        "audit", "candidate_programs", "evaluation_evidence", "episode_evaluations",
        "execution_id", "experiment_id", "model_requests", "outcomes", "report_version", "status",
    )} == {
        "audit": {
            "memory_snapshot_id": None,
            "repairs": [],
            "resource_usage": {"episode_evaluations": 1, "model_requests": 1},
            "retrievals": [],
        },
        "candidate_programs": 1,
        "evaluation_evidence": [],
        "episode_evaluations": 1,
        "execution_id": "exec_000001",
        "experiment_id": validation["experiment_id"],
        "model_requests": 1,
        "outcomes": {"success": 1},
        "report_version": 1,
        "status": "completed",
    }
    assert report["protocol"] == "None"
    assert report["fixed_budget_success_rate"] == 1.0
    assert report["missingness"] == {"incomplete_executions": 0}


def test_cli_exports_and_imports_a_self_verifying_experiment_bundle(tmp_path: Path) -> None:
    specification = tmp_path / "experiment.yaml"
    source_workspace = tmp_path / "source"
    target_workspace = tmp_path / "target"
    bundle = tmp_path / "experiment.bundle.json"
    write_specification(specification)
    validation = json.loads(run_cli("validate", str(specification)).stdout)
    assert run_cli("run", str(specification), "--workspace", str(source_workspace)).returncode == 0

    exported = run_cli(
        "export",
        "--workspace",
        str(source_workspace),
        "--experiment-id",
        validation["experiment_id"],
        "--output",
        str(bundle),
    )
    imported = run_cli("import", "--workspace", str(target_workspace), "--bundle", str(bundle))

    assert exported.returncode == 0, exported.stderr
    assert json.loads(exported.stdout)["checksum"].startswith("sha256:")
    assert imported.returncode == 0, imported.stderr
    assert json.loads(
        run_cli(
            "report",
            "--workspace",
            str(target_workspace),
            "--experiment-id",
            validation["experiment_id"],
        ).stdout
    ) == json.loads(
        run_cli(
            "report",
            "--workspace",
            str(source_workspace),
            "--experiment-id",
            validation["experiment_id"],
        ).stdout
    )
    assert (
        run_cli("import", "--workspace", str(target_workspace), "--bundle", str(bundle)).returncode
        == 2
    )


def test_report_derives_failure_and_replacement_visibility_from_persisted_records(
    tmp_path: Path,
) -> None:
    specification = tmp_path / "experiment.yaml"
    workspace = tmp_path / "workspace"
    write_specification(specification)
    experiment_id = json.loads(run_cli("validate", str(specification)).stdout)["experiment_id"]
    assert run_cli("run", str(specification), "--workspace", str(workspace)).returncode == 0

    from llm_gs.storage import WorkspaceStore

    store = WorkspaceStore(workspace)
    store.record_execution_failure(experiment_id, "exec_000001", "infrastructure", "timeout")
    store.record_execution_failure(experiment_id, None, "model_output", "schema invalid")
    store.record_replacement_execution(experiment_id, "exec_000001")

    report = json.loads(
        run_cli("report", "--workspace", str(workspace), "--experiment-id", experiment_id).stdout
    )
    assert report["failure_classes"] == {
        "infrastructure": 1,
        "model_output": 1,
        "replacements": 1,
    }


def test_invalid_specification_stops_before_execution_work(tmp_path: Path) -> None:
    specification = tmp_path / "invalid.yaml"
    workspace = tmp_path / "must-not-exist"
    specification.write_text(
        """\
spec_version: 1
display_name: offline-smoke
task:
  name: offline.echo
unexpected: true
""",
        encoding="utf-8",
    )

    result = run_cli("run", str(specification), "--workspace", str(workspace))

    assert result.returncode == 2
    assert "unexpected" in result.stderr
    assert not workspace.exists()


def test_unknown_task_fails_before_creating_a_workspace(tmp_path: Path) -> None:
    specification = tmp_path / "unknown-task.yaml"
    workspace = tmp_path / "must-not-exist"
    specification.write_text(
        """\
spec_version: 1
display_name: unknown-task
task:
  name: nonexistent
seeds:
  task: [7]
""",
        encoding="utf-8",
    )

    result = run_cli("run", str(specification), "--workspace", str(workspace))

    assert result.returncode == 2
    assert "offline.echo" in result.stderr
    assert not workspace.exists()


def test_clean_house_regenerate_runs_offline_and_reports_outcome_evidence(
    tmp_path: Path,
) -> None:
    specification = tmp_path / "clean-house.yaml"
    workspace = tmp_path / "workspace"
    specification.write_text(
        """\
spec_version: 1
display_name: clean-house-regenerate
task:
  name: CleanHouse
seeds:
  task: [7]
""",
        encoding="utf-8",
    )

    validation = json.loads(run_cli("validate", str(specification)).stdout)
    assert validation["manifest"]["task"] == {
        "adapter_version": 1,
        "name": "CleanHouse",
        "outcome_classifier_version": 1,
    }

    run = run_cli("run", str(specification), "--workspace", str(workspace))
    assert run.returncode == 0, run.stderr

    report = json.loads(
        run_cli(
            "report",
            "--workspace",
            str(workspace),
            "--experiment-id",
            validation["experiment_id"],
        ).stdout
    )
    assert report["status"] == "completed"
    assert report["outcomes"] == {"partial_completion": 1}
    assert report["evaluation_evidence"][0]["failure_reason"] == "no_markers_collected"


def test_clean_house_execution_recovers_pending_work_after_interruption(tmp_path: Path) -> None:
    specification = tmp_path / "clean-house.yaml"
    workspace = tmp_path / "workspace"
    specification.write_text(
        """\
spec_version: 1
display_name: clean-house-resume
task:
  name: CleanHouse
seeds:
  task: [7, 8]
""",
        encoding="utf-8",
    )
    validation = json.loads(run_cli("validate", str(specification)).stdout)

    interrupted = run_cli(
        "run", str(specification), "--workspace", str(workspace), "--stop-after", "1"
    )
    assert interrupted.returncode == 0, interrupted.stderr
    assert json.loads(interrupted.stdout)["status"] == "interrupted"

    resumed = run_cli(
        "resume",
        "--workspace",
        str(workspace),
        "--experiment-id",
        validation["experiment_id"],
    )
    assert resumed.returncode == 0, resumed.stderr
    assert json.loads(resumed.stdout)["status"] == "completed"

    report = json.loads(
        run_cli(
            "report", "--workspace", str(workspace), "--experiment-id", validation["experiment_id"]
        ).stdout
    )
    assert report["episode_evaluations"] == 2
    assert report["outcomes"] == {"partial_completion": 2}


def test_reflect_strategy_runs_a_repaired_candidate_after_failure(tmp_path: Path) -> None:
    specification = tmp_path / "reflect.yaml"
    specification.write_text(
        """\
spec_version: 1
display_name: clean-house-reflect
task:
  name: CleanHouse
seeds:
  task: [7]
failure_strategy:
  name: reflect
  max_repair_cycles: 3
""",
        encoding="utf-8",
    )

    validation = json.loads(run_cli("validate", str(specification)).stdout)
    assert validation["manifest"]["failure_strategy"] == {
        "name": "reflect",
        "max_repair_cycles": 3,
    }

    workspace = tmp_path / "workspace"
    run = run_cli("run", str(specification), "--workspace", str(workspace))
    assert run.returncode == 0, run.stderr
    report = json.loads(
        run_cli(
            "report",
            "--workspace",
            str(workspace),
            "--experiment-id",
            validation["experiment_id"],
        ).stdout
    )
    assert report["episode_evaluations"] == 2
    assert report["candidate_programs"] == 2

    assert report["model_requests"] == 2


def test_reflect_manifest_reserves_bounded_model_corrections(tmp_path: Path) -> None:
    specification = tmp_path / "reflect-budget.yaml"
    specification.write_text(
        """\
spec_version: 1
display_name: clean-house-reflect-budget
task:
  name: CleanHouse
seeds:
  task: [7]
failure_strategy:
  name: reflect
  max_repair_cycles: 2
""",
        encoding="utf-8",
    )

    manifest = json.loads(run_cli("validate", str(specification)).stdout)["manifest"]

    assert manifest["budgets"]["model_requests"] == 9


def test_reflect_strategy_honors_a_zero_repair_limit(tmp_path: Path) -> None:
    specification = tmp_path / "reflect-zero.yaml"
    workspace = tmp_path / "workspace"
    specification.write_text(
        """\
spec_version: 1
display_name: clean-house-reflect-zero
task:
  name: CleanHouse
seeds:
  task: [7]
failure_strategy:
  name: reflect
  max_repair_cycles: 0
""",
        encoding="utf-8",
    )

    run = run_cli("run", str(specification), "--workspace", str(workspace))

    assert run.returncode == 0, run.stderr
    report = json.loads(
        run_cli(
            "report",
            "--workspace",
            str(workspace),
            "--experiment-id",
            json.loads(run_cli("validate", str(specification)).stdout)["experiment_id"],
        ).stdout
    )
    assert report["candidate_programs"] == 1
    assert report["episode_evaluations"] == 1


def test_memory_repair_runs_with_persisted_memory_context(tmp_path: Path) -> None:
    specification = tmp_path / "memory-repair.yaml"
    workspace = tmp_path / "workspace"
    specification.write_text(
        """\
spec_version: 1
display_name: clean-house-memory-repair
task:
  name: CleanHouse
seeds:
  task: [7]
failure_strategy:
  name: memory_repair
  max_repair_cycles: 3
""",
        encoding="utf-8",
    )
    validation = json.loads(run_cli("validate", str(specification)).stdout)

    run = run_cli("run", str(specification), "--workspace", str(workspace))
    assert run.returncode == 0, run.stderr
    report = json.loads(
        run_cli(
            "report",
            "--workspace",
            str(workspace),
            "--experiment-id",
            validation["experiment_id"],
        ).stdout
    )
    assert report["candidate_programs"] == 2
    assert report["audit"]["memory_snapshot_id"].startswith("snapshot_")
    assert report["audit"]["memory_protocol"] == "online-v1"
    assert report["audit"]["memory_lineage"]["protocol"] == "online-v1"
    assert report["audit"]["memory_lineage"]["parent_snapshot_id"] == report["audit"][
        "memory_snapshot_id"
    ]
    assert report["audit"]["retrievals"]
    retrieval = report["audit"]["retrievals"][0]
    assert retrieval["version"] == 2
    assert retrieval["subsequent_improvement"] is False
    assert retrieval["subsequent_failure_type_changed"] is False
    assert retrieval["subsequent_success"] is False
    assert retrieval["subsequent_attempted"] is True
    assert report["audit"]["repairs"][0]["round"] == 1
    assert report["audit"]["resource_usage"] == {
        "episode_evaluations": 2,
        "model_requests": 2,
    }


def test_memory_repair_evaluates_the_same_full_seed_set_before_and_after_repair(
    tmp_path: Path,
) -> None:
    specification = tmp_path / "memory-repair-multi-seed.yaml"
    workspace = tmp_path / "workspace"
    specification.write_text(
        """\
spec_version: 1
display_name: clean-house-memory-repair-multi-seed
task:
  name: CleanHouse
seeds:
  task: [7, 8]
failure_strategy:
  name: memory_repair
  max_repair_cycles: 1
""",
        encoding="utf-8",
    )

    run = run_cli("run", str(specification), "--workspace", str(workspace))

    assert run.returncode == 0, run.stderr
    report = json.loads(
        run_cli(
            "report",
            "--workspace",
            str(workspace),
            "--experiment-id",
            json.loads(run_cli("validate", str(specification)).stdout)["experiment_id"],
        ).stdout
    )
    assert report["episode_evaluations"] == 4
    assert sum(report["outcomes"].values()) == 4


def test_memory_repair_resumes_with_its_frozen_snapshot(tmp_path: Path) -> None:
    specification = tmp_path / "memory-repair-resume.yaml"
    workspace = tmp_path / "workspace"
    specification.write_text(
        """\
spec_version: 1
display_name: clean-house-memory-repair-resume
task:
  name: CleanHouse
seeds:
  task: [7, 8]
failure_strategy:
  name: memory_repair
  max_repair_cycles: 1
""",
        encoding="utf-8",
    )
    validation = json.loads(run_cli("validate", str(specification)).stdout)

    interrupted = run_cli(
        "run", str(specification), "--workspace", str(workspace), "--stop-after", "1"
    )
    assert json.loads(interrupted.stdout)["status"] == "interrupted"

    resumed = run_cli(
        "resume", "--workspace", str(workspace), "--experiment-id", validation["experiment_id"]
    )

    assert resumed.returncode == 0, resumed.stderr
    assert json.loads(resumed.stdout)["execution_id"] == "exec_000001"


def test_memory_reflect_runs_with_the_frozen_retriever_manifest(tmp_path: Path) -> None:
    specification = tmp_path / "memory-reflect.yaml"
    workspace = tmp_path / "workspace"
    specification.write_text(
        """\
spec_version: 1
display_name: clean-house-memory-reflect
task:
  name: CleanHouse
seeds:
  task: [7]
failure_strategy:
  name: memory_reflect
  max_repair_cycles: 3
""",
        encoding="utf-8",
    )
    validation = json.loads(run_cli("validate", str(specification)).stdout)
    assert (
        validation["manifest"]["memory_snapshot"]["retriever_version"]
        == "structured-clean-house-v3"
    )

    run = run_cli("run", str(specification), "--workspace", str(workspace))
    assert run.returncode == 0, run.stderr


def test_frozen_memory_protocol_uses_isolated_seed_suite_and_reports_held_out_only(
    tmp_path: Path,
) -> None:
    specification = tmp_path / "frozen-memory.yaml"
    workspace = tmp_path / "workspace"
    specification.write_text(
        """\
spec_version: 1
display_name: clean-house-frozen-memory
task:
  name: CleanHouse
seed_suite:
  version: 1
  memory_training: [1]
  development: [2]
  held_out: [3]
failure_strategy:
  name: memory_repair
  max_repair_cycles: 1
""",
        encoding="utf-8",
    )

    validation = json.loads(run_cli("validate", str(specification)).stdout)
    assert validation["manifest"]["memory_snapshot"]["protocol"] == "frozen-v1"
    assert validation["manifest"]["budgets"]["episode_evaluations"] == 4

    run = run_cli("run", str(specification), "--workspace", str(workspace))
    assert run.returncode == 0, run.stderr
    report = json.loads(
        run_cli(
            "report",
            "--workspace",
            str(workspace),
            "--experiment-id",
            validation["experiment_id"],
        ).stdout
    )

    protocol = report["audit"]["frozen_memory_protocol"]
    assert protocol["seed_suite"] == {
        "development": [2],
        "held_out": [3],
        "memory_training": [1],
        "version": 1,
    }
    assert protocol["memory_snapshot_id"].startswith("snapshot_")
    assert protocol["selection"]["selected_before_held_out"] is True
    assert protocol["selection"]["held_out_evaluations"] == 1
    assert protocol["primary_metric"] == {
        "name": "held_out_success_rate",
        "value": 0.0,
    }
    assert report["outcomes"] == {"partial_completion": 1}
    assert report["episode_evaluations"] == 4


def test_seed_suite_rejects_overlapping_partitions(tmp_path: Path) -> None:
    specification = tmp_path / "overlapping.yaml"
    specification.write_text(
        """\
spec_version: 1
display_name: overlapping-seed-suite
task:
  name: CleanHouse
seed_suite:
  version: 1
  memory_training: [1]
  development: [1]
  held_out: [2]
""",
        encoding="utf-8",
    )

    result = run_cli("validate", str(specification))

    assert result.returncode == 2
    assert "disjoint" in result.stderr


def test_frozen_memory_registers_one_manifest_per_task_and_method_arm(tmp_path: Path) -> None:
    first_specification = tmp_path / "first.yaml"
    second_specification = tmp_path / "second.yaml"
    workspace = tmp_path / "workspace"
    specification = """\
spec_version: 1
display_name: frozen-memory
task:
  name: CleanHouse
seed_suite:
  version: 1
  memory_training: [1]
  development: [2]
  held_out: [3]
failure_strategy:
  name: memory_repair
  max_repair_cycles: {cycles}
"""
    first_specification.write_text(specification.format(cycles=1), encoding="utf-8")
    second_specification.write_text(specification.format(cycles=0), encoding="utf-8")

    first = run_cli("run", str(first_specification), "--workspace", str(workspace))
    second = run_cli("run", str(second_specification), "--workspace", str(workspace))

    assert first.returncode == 0, first.stderr
    assert second.returncode == 2
    assert "paired seed suite or budget" in second.stderr


def test_frozen_memory_reuses_its_completed_report_without_repeating_held_out(
    tmp_path: Path,
) -> None:
    specification = tmp_path / "frozen-memory.yaml"
    workspace = tmp_path / "workspace"
    specification.write_text(
        """\
spec_version: 1
display_name: frozen-memory
task:
  name: CleanHouse
seed_suite:
  version: 1
  memory_training: [1]
  development: [2]
  held_out: [3]
failure_strategy:
  name: memory_repair
  max_repair_cycles: 1
""",
        encoding="utf-8",
    )

    first = run_cli("run", str(specification), "--workspace", str(workspace))
    second = run_cli("run", str(specification), "--workspace", str(workspace))

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert json.loads(first.stdout) == json.loads(second.stdout)


def test_experiment_identity_ignores_aliases_but_captures_resolved_components(
    tmp_path: Path,
) -> None:
    first_specification = tmp_path / "first.yaml"
    second_specification = tmp_path / "second.yaml"
    write_specification(first_specification)
    second_specification.write_text(
        first_specification.read_text(encoding="utf-8").replace(
            "display_name: offline-smoke", "display_name: renamed-alias"
        ),
        encoding="utf-8",
    )

    first = json.loads(run_cli("validate", str(first_specification)).stdout)
    second = json.loads(run_cli("validate", str(second_specification)).stdout)

    assert first["experiment_id"] == second["experiment_id"]
    assert first["manifest"] == second["manifest"]
    assert first["manifest"]["components"] == {
            "evaluator": "offline-echo-v1",
        "final_candidate_selector": "lexicographic-v1",
            "proposer": "fake-openai-v1",
        "reporter": "deterministic-json-v1",
    }
    assert first["manifest"]["contracts"] == {
        "parser": "offline-dsl-v1",
        "prompt_sha256": "7f056e1279d0ff8b61e3e30dd2f5fa1faa118287044bca3082d99c8d3b478e29",
    }
    assert first["manifest"]["memory_snapshot"] == {
        "id": "none",
        "read_only": True,
        "retriever_order": (
            "task,failure_type,failure_reason,state_distance,evidence_quality,"
            "improvement,novelty,normalized_ast_hash,entry_id"
        ),
        "retriever_version": "structured-clean-house-v3",
        "retriever_weights": "1,1,1,1,1,1,1,1,1",
    }
