from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from llm_gs.v1_adapter import V1Adapter, V1ExecutionLimits
from prog_policies.base import BaseTask
from prog_policies.runtime import create_replay_environment


def evaluate_v1_baseline(
    task_name: str,
    program_source: str,
    seed: int,
    limits: V1ExecutionLimits,
) -> dict[str, object]:
    execution_target, dsl = create_replay_environment(
        task_name,
        seed,
        {
            "crashable": limits.crashable,
            "crash_penalty": limits.crash_penalty,
            "max_calls": limits.max_calls,
        },
    )
    reward = execution_target.evaluate_program(dsl.parse_str_to_node(program_source))
    environment = (
        execution_target.get_environment()
        if isinstance(execution_target, BaseTask)
        else execution_target
    )
    terminal_state = json.dumps(
        environment.get_state().tolist(), separators=(",", ":")
    ) if task_name in {"CleanHouse", "FourCorners"} else json.dumps(
        {
            "agent_dir": int(environment.unwrapped.agent_dir),
            "agent_pos": [int(value) for value in environment.unwrapped.agent_pos],
            "grid": environment.unwrapped.grid.encode().tolist(),
        },
        separators=(",", ":"),
    )

    return {
        "terminal_state": terminal_state,
        "reward": reward,
        "crashed": environment.is_crashed(),
        "program_call_count": environment.num_calls,
    }


@pytest.mark.parametrize(
    ("task_name", "program_source", "seed", "limits"),
    [
        ("CleanHouse", "DEF run m( turnLeft m)", 7, V1ExecutionLimits(max_calls=10)),
        ("FourCorners", "DEF run m( turnLeft m)", 7, V1ExecutionLimits(max_calls=10)),
        (
            "CleanHouse",
            "DEF run m( REPEAT R=2 r( turnLeft r) m)",
            7,
            V1ExecutionLimits(max_calls=1),
        ),
        ("RedBlueDoor", "DEF run m( left m)", 11, V1ExecutionLimits(max_calls=10)),
        (
            "RedBlueDoor",
            "DEF run m( REPEAT R=2 r( left r) m)",
            11,
            V1ExecutionLimits(max_calls=1),
        ),
    ],
)
def test_v1_adapter_matches_deterministic_v1_execution(
    task_name: str,
    program_source: str,
    seed: int,
    limits: V1ExecutionLimits,
) -> None:
    baseline = evaluate_v1_baseline(task_name, program_source, seed, limits)

    result = V1Adapter().evaluate(task_name, program_source, seed, limits)

    assert asdict(result) == baseline


def test_clean_house_adapter_emits_versioned_partial_completion_evidence() -> None:
    result = V1Adapter().evaluate_attempt(
        "CleanHouse", "DEF run m( turnLeft m)", 7, V1ExecutionLimits(max_calls=10)
    )

    assert result.outcome == "partial_completion"
    assert result.normalized_progress == 0.0
    assert result.failure_type == "task_failure"
    assert result.failure_reason == "no_markers_collected"
    assert result.evaluation_evidence == {
        "version": 1,
        "initial_marker_count": 11,
        "remaining_marker_count": 11,
        "program_call_count": 1,
        "terminal_state": result.terminal_state,
    }


def test_four_corners_adapter_emits_versioned_goal_progress_evidence() -> None:
    result = V1Adapter().evaluate_attempt(
        "FourCorners", "DEF run m( turnLeft m)", 7, V1ExecutionLimits(max_calls=10)
    )

    assert result.outcome == "partial_completion"
    assert result.normalized_progress == 0.0
    assert result.failure_type == "task_failure"
    assert result.failure_reason == "no_corner_markers_placed"
    assert result.evaluation_evidence == {
        "version": 1,
        "goal_marker_count": 4,
        "correct_marker_count": 0,
        "placed_marker_count": 0,
        "incorrect_marker_count": 0,
        "program_call_count": 1,
        "terminal_state": result.terminal_state,
    }


def test_equivalence_failure_blocks_baseline_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = V1Adapter()
    monkeypatch.setattr(
        adapter,
        "evaluate",
        lambda *_: type("Mismatch", (), {"terminal_state": "wrong"})(),
    )

    with pytest.raises(ValueError, match="baseline selection is blocked"):
        adapter.assert_equivalent("CleanHouse", "DEF run m( turnLeft m)", 7, V1ExecutionLimits(10))
