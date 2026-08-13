from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from llm_gs.ast_features import normalized_ast_hash
from llm_gs.contracts import CandidateProgram, EpisodeResult
from llm_gs.memory import (
    StructuredRetriever,
    curate_door_key_attempt,
    serialize_repair_context,
)
from llm_gs.minigrid_door_key import DoorKeyLimits, MiniGridDoorKeyAdapter
from llm_gs.proposer import _validate_dsl


def _candidate() -> CandidateProgram:
    return CandidateProgram(source="DEF run m( left m)")


def test_door_key_replay_reproduces_terminal_state_and_evidence() -> None:
    adapter = MiniGridDoorKeyAdapter()
    first = adapter.evaluate(_candidate(), seed=7, limits=DoorKeyLimits(max_calls=10))
    second = adapter.evaluate(_candidate(), seed=7, limits=DoorKeyLimits(max_calls=10))

    assert first == second
    assert first.terminal_state == second.terminal_state
    assert first.evaluation_evidence is not None
    assert first.evaluation_evidence["program_call_count"] == 1
    assert first.evaluation_evidence["movement"]["initial_position"] != []
    assert first.evaluation_evidence["initial_key_position"] != []
    assert first.evaluation_evidence["initial_door_position"] != []
    assert first.evaluation_evidence["initial_goal_position"] != []


def test_door_key_adapter_matches_the_v1_minigrid_runtime() -> None:
    MiniGridDoorKeyAdapter().assert_equivalent(
        _candidate(), seed=11, limits=DoorKeyLimits(max_calls=10)
    )


def test_door_key_memory_uses_key_door_goal_initial_geometry() -> None:
    result = EpisodeResult(
        outcome="partial_completion",
        failure_type="task_failure",
        failure_reason="key_not_collected",
        evaluation_evidence={
            "initial_key_position": [2, 3],
            "initial_door_position": [4, 3],
            "initial_goal_position": [6, 5],
            "key_collected": False,
            "door_unlocked": False,
            "goal_completed": False,
        },
    )
    close = curate_door_key_attempt("close", _candidate().source, result)
    far = curate_door_key_attempt(
        "far",
        "DEF run m( right m)",
        result.model_copy(
            update={
                "evaluation_evidence": {
                    **result.evaluation_evidence,
                    "initial_key_position": [1, 1],
                    "initial_door_position": [6, 1],
                    "initial_goal_position": [6, 6],
                }
            }
        ),
    )

    entries, _ = StructuredRetriever((far, close), task="DoorKey").retrieve(result)
    context = serialize_repair_context(result, entries)

    assert entries == [close, far]
    assert '"door_column":4' in context
    assert '"goal_row":5' in context


def test_minigrid_dsl_uses_normalized_ast_features_and_validation() -> None:
    source = _candidate().source

    _validate_dsl(source)

    assert normalized_ast_hash(source) == normalized_ast_hash("DEF run m(  left m )")


def test_door_key_rejects_karel_only_dsl_before_execution() -> None:
    with pytest.raises(Exception, match="Unrecognized token"):
        _validate_dsl("DEF run m( turnLeft m)", task_name="DoorKey")


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("OPENAI_API_KEY", None)
    return subprocess.run(
        ["llm-gs", *args], check=False, capture_output=True, text=True, env=environment
    )


@pytest.mark.parametrize(
    "strategy", ["regenerate", "reflect", "memory_repair", "memory_reflect"]
)
def test_door_key_failure_strategies_keep_equal_budget_contracts(
    tmp_path: Path, strategy: str
) -> None:
    specification = tmp_path / f"door-key-{strategy}.yaml"
    workspace = tmp_path / "workspace"
    specification.write_text(
        f"""\
spec_version: 1
display_name: door-key-{strategy}
task:
  name: DoorKey
seeds:
  task: [7]
failure_strategy:
  name: {strategy}
  max_repair_cycles: 1
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

    assert validation["manifest"]["components"]["evaluator"] == "minigrid-doorkey-adapter-v1"
    assert validation["manifest"]["budgets"] == {
        "episode_evaluations": 2,
        "input_tokens": 4096,
        "model_requests": 6,
        "output_tokens": 1024,
    }
    evidence = report["evaluation_evidence"][0]["evidence"]
    assert evidence["initial_key_position"]
    assert evidence["initial_door_position"]
    assert evidence["initial_goal_position"]
    if strategy.startswith("memory_"):
        assert report["audit"]["retrievals"][0]["candidate_components"]
