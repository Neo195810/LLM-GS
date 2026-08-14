from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from llm_gs.ast_features import normalized_ast_hash
from llm_gs.contracts import CandidateProgram
from llm_gs.proposer import _validate_dsl
from llm_gs.textworld_pilot import TextWorldPilotAdapter, TextWorldPilotLimits
from llm_gs.textworld_release_gate import (
    REQUIRED_EVIDENCE_CLASSES,
    EvidenceClassRecord,
    ReplayArtifact,
    TextWorldReleaseEvidence,
    evaluate_release_gate,
)

_SUCCESS_SOURCE = (
    "WHEN not_has_key DO take_key; WHEN has_key DO unlock_chest; "
    "WHEN chest_unlocked DO open_chest"
)


def test_textworld_pilot_compiles_only_the_fixed_vocabulary_quest() -> None:
    _validate_dsl(_SUCCESS_SOURCE, task_name="TextWorldPilot")

    with pytest.raises(ValueError, match="unrecognized predicate or action"):
        _validate_dsl("take brass key", task_name="TextWorldPilot")

    assert normalized_ast_hash(_SUCCESS_SOURCE, "TextWorldPilot") == normalized_ast_hash(
        " WHEN not_has_key DO take_key ; WHEN has_key DO unlock_chest ; "
        "WHEN chest_unlocked DO open_chest ",
        "TextWorldPilot",
    )


def test_textworld_pilot_replays_facts_commands_and_explicit_win_fail_facts() -> None:
    adapter = TextWorldPilotAdapter()
    candidate = CandidateProgram(source=_SUCCESS_SOURCE)
    first = adapter.evaluate(candidate, seed=41, limits=TextWorldPilotLimits(max_actions=3))
    second = adapter.evaluate(candidate, seed=41, limits=TextWorldPilotLimits(max_actions=3))

    assert first == second
    assert first.outcome == "success"
    assert first.evaluation_evidence["commands"] == [
        "take key",
        "unlock chest with key",
        "open chest",
    ]
    assert first.evaluation_evidence["facts"] == [
        "at(P, vault)",
        "at(chest, vault)",
        "in(key, I)",
        "match(key, chest)",
        "open(chest)",
    ]
    assert first.evaluation_evidence["win_facts"] == ["open(chest)"]
    assert first.evaluation_evidence["fail_facts"] == ["in(key, chest)"]
    assert first.evaluation_evidence["won"] is True
    assert first.evaluation_evidence["lost"] is False


def test_textworld_release_gate_does_not_promote_partial_evidence() -> None:
    gate = evaluate_release_gate(
        TextWorldReleaseEvidence(
            python311_installation=True,
            license_reviewed=False,
            replay_artifacts=(),
            evidence_records=(),
            single_episode_p95_ms=None,
            batch_episode_p95_ms=None,
            peak_memory_mb=None,
            trace_bytes_p95=None,
        )
    )

    assert not gate.passed
    assert gate.unmet_requirements == (
        "license_review",
        "100_seed_cross_process_replay",
        "structured_evidence",
        "measured_performance",
    )


def test_textworld_release_gate_requires_and_accepts_all_formal_gates() -> None:
    gate = evaluate_release_gate(
        TextWorldReleaseEvidence(
            python311_installation=True,
            license_reviewed=True,
            replay_artifacts=tuple(
                ReplayArtifact(seed, process, "terminal", "sha256:evidence", 1.0, 3)
                for seed in range(100)
                for process in ("process-a", "process-b")
            ),
            evidence_records=tuple(
                EvidenceClassRecord(name, "observed", "recorded by adapter")
                for name in REQUIRED_EVIDENCE_CLASSES
            ),
            single_episode_p95_ms=10.0,
            batch_episode_p95_ms=4.0,
            peak_memory_mb=128.0,
            trace_bytes_p95=1024,
        )
    )

    assert gate.passed
    assert gate.unmet_requirements == ()


def test_textworld_release_gate_rejects_non_finite_measurements() -> None:
    gate = evaluate_release_gate(
        TextWorldReleaseEvidence(
            python311_installation=True,
            license_reviewed=True,
            replay_artifacts=tuple(
                ReplayArtifact(seed, process, "terminal", "sha256:evidence", 1.0, 3)
                for seed in range(100)
                for process in ("process-a", "process-b")
            ),
            evidence_records=tuple(
                EvidenceClassRecord(name, "observed", "recorded by adapter")
                for name in REQUIRED_EVIDENCE_CLASSES
            ),
            single_episode_p95_ms=float("nan"),
            batch_episode_p95_ms=4.0,
            peak_memory_mb=128.0,
            trace_bytes_p95=1024,
        )
    )

    assert gate.unmet_requirements == ("measured_performance",)


def test_textworld_formal_promotion_cli_requires_persisted_gate_evidence(tmp_path: Path) -> None:
    evidence = tmp_path / "textworld-release-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "python311_installation": True,
                "license_reviewed": True,
                "replay_artifacts": [
                    {
                        "seed": seed,
                        "process_id": process,
                        "terminal_state": "won",
                        "evidence_sha256": "sha256:fixed",
                        "score": 1.0,
                        "action_count": 3,
                    }
                    for seed in range(100)
                    for process in ("pid-100", "pid-200")
                ],
                "evidence_records": [
                    {"name": name, "status": "observed", "detail": "artifact"}
                    for name in REQUIRED_EVIDENCE_CLASSES
                ],
                "single_episode_p95_ms": 10.0,
                "batch_episode_p95_ms": 4.0,
                "peak_memory_mb": 128.0,
                "trace_bytes_p95": 1024,
            }
        ),
        encoding="utf-8",
    )

    completed = _run_cli("textworld", "promote", "--evidence", str(evidence))

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "passed": True,
        "unmet_requirements": [],
    }


def test_textworld_formal_promotion_cli_rejects_invalid_evidence(tmp_path: Path) -> None:
    evidence = tmp_path / "incomplete.json"
    evidence.write_text("{}", encoding="utf-8")

    completed = _run_cli("textworld", "promote", "--evidence", str(evidence))

    assert completed.returncode == 2
    assert "invalid TextWorld release evidence" in completed.stderr


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("OPENAI_API_KEY", None)
    return subprocess.run(
        ["llm-gs", *args], check=False, capture_output=True, text=True, env=environment
    )


def test_textworld_pilot_runs_through_the_v2_adapter_boundary(tmp_path: Path) -> None:
    specification = tmp_path / "textworld-pilot.yaml"
    workspace = tmp_path / "workspace"
    specification.write_text(
        """\
spec_version: 1
display_name: textworld-pilot
task:
  name: TextWorldPilot
seeds:
  task: [3]
""",
        encoding="utf-8",
    )

    validation = json.loads(_run_cli("validate", str(specification)).stdout)
    run = _run_cli("run", str(specification), "--workspace", str(workspace))
    assert run.returncode == 0, run.stderr
    report = json.loads(
        _run_cli(
            "report", "--workspace", str(workspace), "--experiment-id", validation["experiment_id"]
        ).stdout
    )

    assert validation["manifest"]["components"]["evaluator"] == "textworld-pilot-adapter-v1"
    assert validation["manifest"]["contracts"]["parser"] == "textworld-pilot-dsl-v1"
    assert report["outcomes"] == {"success": 1}
    assert report["evaluation_evidence"][0]["evidence"]["win_facts"] == ["open(chest)"]
