from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from llm_gs.contracts import CandidateProgram, EpisodeResult
from llm_gs.memory import StructuredRetriever, curate_red_blue_door_attempt
from llm_gs.minigrid_red_blue_door import RedBlueDoorAdapter, RedBlueDoorLimits


def _candidate() -> CandidateProgram:
    return CandidateProgram(source="DEF run m( left m)")


def test_red_blue_door_replay_and_v1_equivalence_are_deterministic() -> None:
    adapter = RedBlueDoorAdapter()
    first = adapter.evaluate(_candidate(), seed=11, limits=RedBlueDoorLimits(max_calls=10))
    second = adapter.evaluate(_candidate(), seed=11, limits=RedBlueDoorLimits(max_calls=10))

    assert first == second
    assert first.evaluation_evidence is not None
    assert first.evaluation_evidence["program_call_count"] == 1
    assert first.evaluation_evidence["initial_red_door_position"]
    assert first.evaluation_evidence["initial_blue_door_position"]
    assert first.evaluation_evidence["door_order"] == "none"
    adapter.assert_equivalent(_candidate(), seed=11, limits=RedBlueDoorLimits(max_calls=10))


@pytest.mark.parametrize(
    ("source", "limits", "expected_order"),
    [
        ("DEF run m( left forward left toggle m)", RedBlueDoorLimits(30), "blue_before_red"),
        (
            "DEF run m( forward forward forward left forward right toggle right right "
            "forward forward forward toggle m)",
            RedBlueDoorLimits(100),
            "red_then_blue",
        ),
        ("DEF run m( REPEAT R=2 r( left r) m)", RedBlueDoorLimits(1), "none"),
    ],
)
def test_red_blue_door_fixed_programs_match_v1_across_ordering_branches(
    source: str, limits: RedBlueDoorLimits, expected_order: str
) -> None:
    adapter = RedBlueDoorAdapter()
    candidate = CandidateProgram(source=source)

    adapter.assert_equivalent(candidate, seed=11, limits=limits)

    evidence = adapter.evaluate(candidate, seed=11, limits=limits).evaluation_evidence
    assert evidence is not None
    assert evidence["door_order"] == expected_order


def test_red_blue_door_classifies_ordering_partial_progress() -> None:
    result = EpisodeResult(
        outcome="partial_completion",
        failure_type="task_failure",
        failure_reason="red_door_not_opened",
        evaluation_evidence={
            "initial_red_door_position": [3, 2],
            "initial_blue_door_position": [8, 4],
            "red_door_opened": False,
            "blue_door_opened": False,
            "red_opened_before_blue": False,
        },
    )
    entry = curate_red_blue_door_attempt("red-blue", _candidate().source, result)
    selected, outcome = StructuredRetriever((entry,), task="RedBlueDoor").retrieve(result)

    assert selected == [entry]
    assert outcome.candidate_components[entry.entry_id].state_distance == 0


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("OPENAI_API_KEY", None)
    return subprocess.run(
        ["llm-gs", *args], check=False, capture_output=True, text=True, env=environment
    )


@pytest.mark.parametrize(
    "strategy", ["regenerate", "reflect", "memory_repair", "memory_reflect"]
)
def test_red_blue_door_failure_strategies_share_budget_contracts(
    tmp_path: Path, strategy: str
) -> None:
    specification = tmp_path / f"red-blue-door-{strategy}.yaml"
    workspace = tmp_path / "workspace"
    specification.write_text(
        f"""\
spec_version: 1
display_name: red-blue-door-{strategy}
task:
  name: RedBlueDoor
seeds:
  task: [11]
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

    assert validation["manifest"]["components"]["evaluator"] == "minigrid-redbluedoor-adapter-v1"
    assert validation["manifest"]["budgets"] == {
        "episode_evaluations": 2,
        "input_tokens": 4096,
        "model_requests": 6,
        "output_tokens": 1024,
    }
    evidence = report["evaluation_evidence"][0]["evidence"]
    assert evidence["initial_red_door_position"]
    assert evidence["initial_blue_door_position"]
    if strategy.startswith("memory_"):
        assert report["audit"]["retrievals"][0]["candidate_components"]
