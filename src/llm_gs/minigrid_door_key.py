from __future__ import annotations

import json
from dataclasses import dataclass
from typing import cast

from minigrid.core.grid import Grid
from minigrid.core.world_object import Door, Goal, Key
from minigrid.envs import DoorKeyEnv  # type: ignore[attr-defined]
from minigrid.minigrid_env import MiniGridEnv

from llm_gs.contracts import CandidateProgram, EpisodeResult
from prog_policies.minigrid.dsl import MinigridDSL
from prog_policies.minigrid.wrapper import ProgramWrapper


@dataclass(frozen=True)
class DoorKeyLimits:
    max_calls: int


class MiniGridDoorKeyAdapter:
    """V2 adapter over the existing deterministic MiniGrid runtime."""

    def evaluate(
        self, candidate: CandidateProgram, seed: int, limits: DoorKeyLimits
    ) -> EpisodeResult:
        return _classify_baseline(_evaluate_v1_minigrid_baseline(candidate, seed, limits))

    def assert_equivalent(
        self, candidate: CandidateProgram, seed: int, limits: DoorKeyLimits
    ) -> None:
        """Verify the V2 adapter against a fresh execution of the V1 runtime."""
        adapter_result = self.evaluate(candidate, seed, limits)
        baseline = _evaluate_v1_minigrid_baseline(candidate, seed, limits)
        evidence = adapter_result.evaluation_evidence or {}
        if (
            adapter_result.terminal_state != baseline.terminal_state
            or evidence.get("score") != baseline.reward
            or evidence.get("program_call_count") != baseline.program_call_count
            or (adapter_result.outcome == "policy_crash") != baseline.crashed
        ):
            raise AssertionError("MiniGrid DoorKey adapter differs from the V1 runtime")


def evaluate_door_key(
    candidate: CandidateProgram, seed: int, limits: DoorKeyLimits
) -> EpisodeResult:
    return MiniGridDoorKeyAdapter().evaluate(candidate, seed, limits)


@dataclass(frozen=True)
class _MiniGridDoorKeyBaseline:
    initial_state: dict[str, int | list[int] | None]
    final_state: dict[str, int | list[int] | None]
    terminal_state: str
    reward: float
    crashed: bool
    program_call_count: int
    key_collected: bool
    door_unlocked: bool
    goal_completed: bool
    truncated: bool


def _evaluate_v1_minigrid_baseline(
    candidate: CandidateProgram, seed: int, limits: DoorKeyLimits
) -> _MiniGridDoorKeyBaseline:
    environment = ProgramWrapper(DoorKeyEnv(size=8), seed, max_calls=limits.max_calls)
    environment.reset()
    initial_state = _world_state(environment)
    reward = environment.evaluate_program(
        MinigridDSL().parse_str_to_node(candidate.source)  # type: ignore[no-untyped-call]
    )
    final_state = _world_state(environment)
    key_collected = _is_key_collected(environment, initial_state["key_position"])
    door_unlocked = _is_door_unlocked(environment, initial_state["door_position"])
    goal_completed = bool(environment.terminated)
    truncated = bool(
        not goal_completed
        and _minigrid_environment(environment).step_count
        >= _minigrid_environment(environment).max_steps
    )
    return _MiniGridDoorKeyBaseline(
        initial_state=initial_state,
        final_state=final_state,
        terminal_state=_terminal_state(environment),
        reward=reward,
        crashed=environment.is_crashed(),  # type: ignore[no-untyped-call]
        program_call_count=environment.num_calls,
        key_collected=key_collected,
        door_unlocked=door_unlocked,
        goal_completed=goal_completed,
        truncated=truncated,
    )


def _classify_baseline(baseline: _MiniGridDoorKeyBaseline) -> EpisodeResult:
    evidence: dict[str, object] = {
        "version": 1,
        "initial_key_position": baseline.initial_state["key_position"],
        "initial_door_position": baseline.initial_state["door_position"],
        "initial_goal_position": baseline.initial_state["goal_position"],
        "key_collected": baseline.key_collected,
        "door_unlocked": baseline.door_unlocked,
        "goal_completed": baseline.goal_completed,
        "truncated": baseline.truncated,
        "score": baseline.reward,
        "program_call_count": baseline.program_call_count,
        "movement": {
            "initial_position": baseline.initial_state["agent_position"],
            "initial_direction": baseline.initial_state["agent_direction"],
            "final_position": baseline.final_state["agent_position"],
            "final_direction": baseline.final_state["agent_direction"],
        },
        "terminal_state": baseline.terminal_state,
    }
    progress = (
        1.0
        if baseline.goal_completed
        else 0.6
        if baseline.door_unlocked
        else 0.3
        if baseline.key_collected
        else 0.0
    )
    terminal_state = str(evidence["terminal_state"])
    if baseline.crashed:
        return EpisodeResult(
            outcome="policy_crash",
            normalized_progress=progress,
            failure_type="policy_failure",
            failure_reason="call_limit_exhausted",
            evaluation_evidence=evidence,
            terminal_state=terminal_state,
        )
    if baseline.goal_completed:
        return EpisodeResult(
            outcome="success",
            normalized_progress=1.0,
            evaluation_evidence=evidence,
            terminal_state=terminal_state,
        )
    reason = (
        "key_not_collected"
        if not baseline.key_collected
        else "door_not_unlocked"
        if not baseline.door_unlocked
        else "goal_not_reached"
    )
    return EpisodeResult(
        outcome="partial_completion",
        normalized_progress=progress,
        failure_type="task_failure",
        failure_reason=reason,
        evaluation_evidence=evidence,
        terminal_state=terminal_state,
    )


def _world_state(environment: ProgramWrapper) -> dict[str, int | list[int] | None]:
    unwrapped = _minigrid_environment(environment)
    grid = unwrapped.grid
    return {
        "key_position": _position(grid, Key),
        "door_position": _position(grid, Door),
        "goal_position": _position(grid, Goal),
        "agent_position": [int(value) for value in unwrapped.agent_pos],
        "agent_direction": int(unwrapped.agent_dir),
    }


def _is_key_collected(environment: ProgramWrapper, initial_position: object) -> bool:
    unwrapped = _minigrid_environment(environment)
    if isinstance(unwrapped.carrying, Key):
        return True
    if not isinstance(initial_position, list) or len(initial_position) != 2:
        return False
    return not isinstance(unwrapped.grid.get(*initial_position), Key)


def _is_door_unlocked(environment: ProgramWrapper, initial_position: object) -> bool:
    if not isinstance(initial_position, list) or len(initial_position) != 2:
        return False
    door = _minigrid_environment(environment).grid.get(*initial_position)
    return isinstance(door, Door) and not door.is_locked


def _position(grid: Grid, object_type: type[object]) -> list[int] | None:
    width = int(grid.width)
    height = int(grid.height)
    for column in range(width):
        for row in range(height):
            if isinstance(grid.get(column, row), object_type):
                return [column, row]
    return None


def _terminal_state(environment: ProgramWrapper) -> str:
    unwrapped = _minigrid_environment(environment)
    return json.dumps(
        {
            "agent_dir": int(unwrapped.agent_dir),
            "agent_pos": [int(value) for value in unwrapped.agent_pos],
            "grid": unwrapped.grid.encode().tolist(),
        },
        separators=(",", ":"),
    )


def _minigrid_environment(environment: ProgramWrapper) -> MiniGridEnv:
    return cast(MiniGridEnv, environment.unwrapped)
