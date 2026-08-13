from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

from minigrid.core.grid import Grid
from minigrid.core.world_object import Door
from minigrid.minigrid_env import MiniGridEnv

from llm_gs.contracts import CandidateProgram, EpisodeResult
from prog_policies.minigrid.dsl import MinigridDSL
from prog_policies.minigrid.wrapper import ProgramWrapper
from prog_policies.minigrid_tasks.redbluedoor import RedBlueDoor


@dataclass(frozen=True)
class RedBlueDoorLimits:
    max_calls: int


@dataclass(frozen=True)
class _RedBlueDoorBaseline:
    initial_state: dict[str, int | list[int] | None]
    final_state: dict[str, int | list[int] | None]
    terminal_state: str
    reward: float
    crashed: bool
    program_call_count: int
    red_door_opened: bool
    blue_door_opened: bool
    red_opened_before_blue: bool


class RedBlueDoorAdapter:
    """Classify the existing V1 MiniGrid RedBlueDoor execution deterministically."""

    def evaluate(
        self, candidate: CandidateProgram, seed: int, limits: RedBlueDoorLimits
    ) -> EpisodeResult:
        return _classify(_evaluate_v1_baseline(candidate, seed, limits))

    def assert_equivalent(
        self, candidate: CandidateProgram, seed: int, limits: RedBlueDoorLimits
    ) -> None:
        result = self.evaluate(candidate, seed, limits)
        baseline = _evaluate_v1_baseline(candidate, seed, limits)
        evidence = result.evaluation_evidence or {}
        if (
            result.terminal_state != baseline.terminal_state
            or evidence.get("score") != baseline.reward
            or evidence.get("program_call_count") != baseline.program_call_count
            or evidence.get("v1_crashed") != baseline.crashed
        ):
            raise AssertionError("RedBlueDoor adapter differs from the V1 runtime")


def _evaluate_v1_baseline(
    candidate: CandidateProgram, seed: int, limits: RedBlueDoorLimits
) -> _RedBlueDoorBaseline:
    environment = cast(
        ProgramWrapper, RedBlueDoor(seed=seed, max_calls=limits.max_calls)  # type: ignore[no-untyped-call]
    )
    environment.reset()
    initial_state = _world_state(environment)
    reward = environment.evaluate_program(
        MinigridDSL().parse_str_to_node(candidate.source)  # type: ignore[no-untyped-call]
    )
    final_state = _world_state(environment)
    red_door_opened = _door_is_open(environment, "red")
    blue_door_opened = _door_is_open(environment, "blue")
    red_opened_before_blue = bool(cast(Any, _environment(environment)).get_first_reward)
    return _RedBlueDoorBaseline(
        initial_state=initial_state,
        final_state=final_state,
        terminal_state=_terminal_state(environment),
        reward=reward,
        crashed=environment.is_crashed(),  # type: ignore[no-untyped-call]
        program_call_count=environment.num_calls,
        red_door_opened=red_door_opened,
        blue_door_opened=blue_door_opened,
        red_opened_before_blue=red_opened_before_blue,
    )


def _classify(baseline: _RedBlueDoorBaseline) -> EpisodeResult:
    success = baseline.red_opened_before_blue and baseline.blue_door_opened
    door_order = (
        "red_then_blue"
        if success
        else "blue_before_red"
        if baseline.blue_door_opened
        else "red_only"
        if baseline.red_door_opened
        else "none"
    )
    progress = 1.0 if success else 0.5 if baseline.red_door_opened else 0.0
    evidence: dict[str, object] = {
        "version": 1,
        "initial_red_door_position": baseline.initial_state["red_door_position"],
        "initial_blue_door_position": baseline.initial_state["blue_door_position"],
        "red_door_opened": baseline.red_door_opened,
        "blue_door_opened": baseline.blue_door_opened,
        "red_opened_before_blue": baseline.red_opened_before_blue,
        "door_order": door_order,
        "goal_completed": success,
        "score": baseline.reward,
        "v1_crashed": baseline.crashed,
        "program_call_count": baseline.program_call_count,
        "movement": {
            "initial_position": baseline.initial_state["agent_position"],
            "initial_direction": baseline.initial_state["agent_direction"],
            "final_position": baseline.final_state["agent_position"],
            "final_direction": baseline.final_state["agent_direction"],
        },
        "terminal_state": baseline.terminal_state,
    }
    if success:
        return EpisodeResult(
            outcome="success",
            normalized_progress=1.0,
            evaluation_evidence=evidence,
            terminal_state=baseline.terminal_state,
        )
    if baseline.crashed:
        return EpisodeResult(
            outcome="policy_crash",
            normalized_progress=progress,
            failure_type="policy_failure",
            failure_reason="call_limit_exhausted",
            evaluation_evidence=evidence,
            terminal_state=baseline.terminal_state,
        )
    reason = (
        "blue_opened_before_red"
        if baseline.blue_door_opened
        else "red_door_opened_blue_remaining"
        if baseline.red_door_opened
        else "red_door_not_opened"
    )
    return EpisodeResult(
        outcome="partial_completion",
        normalized_progress=progress,
        failure_type="task_failure",
        failure_reason=reason,
        evaluation_evidence=evidence,
        terminal_state=baseline.terminal_state,
    )


def _world_state(environment: ProgramWrapper) -> dict[str, int | list[int] | None]:
    grid = _environment(environment).grid
    return {
        "red_door_position": _door_position(grid, "red"),
        "blue_door_position": _door_position(grid, "blue"),
        "agent_position": [int(value) for value in _environment(environment).agent_pos],
        "agent_direction": int(_environment(environment).agent_dir),
    }


def _door_position(grid: Grid, color: str) -> list[int] | None:
    for column in range(grid.width):
        for row in range(grid.height):
            door = grid.get(column, row)
            if isinstance(door, Door) and door.color == color:
                return [column, row]
    return None


def _door_is_open(environment: ProgramWrapper, color: str) -> bool:
    position = _door_position(_environment(environment).grid, color)
    if position is None:
        return False
    door = _environment(environment).grid.get(*position)
    return isinstance(door, Door) and door.is_open


def _terminal_state(environment: ProgramWrapper) -> str:
    unwrapped = _environment(environment)
    return json.dumps(
        {
            "agent_dir": int(unwrapped.agent_dir),
            "agent_pos": [int(value) for value in unwrapped.agent_pos],
            "grid": unwrapped.grid.encode().tolist(),
        },
        separators=(",", ":"),
    )


def _environment(environment: ProgramWrapper) -> MiniGridEnv:
    return cast(MiniGridEnv, environment.unwrapped)
