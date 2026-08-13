from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from prog_policies.base.task import BaseTask
from prog_policies.runtime import create_replay_environment

V1TaskName = Literal["CleanHouse", "FourCorners", "RedBlueDoor"]


@dataclass(frozen=True)
class V1ExecutionLimits:
    max_calls: int
    crashable: bool = False
    crash_penalty: float = 0.0


@dataclass(frozen=True)
class V1ExecutionResult:
    terminal_state: str
    reward: float
    crashed: bool
    program_call_count: int


@dataclass(frozen=True)
class V1AttemptResult:
    """A versioned Karel Task outcome derived from deterministic V1 facts."""

    outcome: Literal["success", "partial_completion", "policy_crash"]
    normalized_progress: float
    failure_type: str | None
    failure_reason: str | None
    evaluation_evidence: dict[str, object]
    terminal_state: str


class V1Adapter:
    """Execute fixed V1 DSL programs through the V2 baseline boundary."""

    def evaluate(
        self,
        task_name: V1TaskName,
        program_source: str,
        seed: int,
        limits: V1ExecutionLimits,
    ) -> V1ExecutionResult:
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
        return V1ExecutionResult(
            terminal_state=_terminal_state(task_name, environment),
            reward=reward,
            crashed=environment.is_crashed(),
            program_call_count=environment.num_calls,
        )

    def evaluate_attempt(
        self,
        task_name: Literal["CleanHouse", "FourCorners"],
        program_source: str,
        seed: int,
        limits: V1ExecutionLimits,
    ) -> V1AttemptResult:
        """Classify one Karel evaluation without changing V1 execution behavior."""
        execution_target, dsl = create_replay_environment(
            task_name,
            seed,
            {
                "crashable": limits.crashable,
                "crash_penalty": limits.crash_penalty,
                "max_calls": limits.max_calls,
            },
        )
        if not isinstance(execution_target, BaseTask):
            raise ValueError(f"{task_name} does not expose a V1 task environment")
        execution_target.evaluate_program(dsl.parse_str_to_node(program_source))
        environment: Any = execution_target.get_environment()
        terminal_state = _terminal_state(task_name, environment)
        if task_name == "FourCorners":
            four_corners_task: Any = execution_target
            goal_markers = four_corners_task.goal_markers
            goal_marker_count = len(goal_markers)
            correct_marker_count = sum(
                int(environment.markers_grid[row, column] > 0)
                for row, column in goal_markers
            )
            placed_marker_count = int(environment.markers_grid.sum())
            incorrect_marker_count = placed_marker_count - correct_marker_count
            evidence = {
                "version": 1,
                "goal_marker_count": goal_marker_count,
                "correct_marker_count": correct_marker_count,
                "placed_marker_count": placed_marker_count,
                "incorrect_marker_count": incorrect_marker_count,
                "program_call_count": environment.num_calls,
                "terminal_state": terminal_state,
            }
            if environment.is_crashed():
                return V1AttemptResult(
                    "policy_crash", correct_marker_count / goal_marker_count,
                    "policy_failure", "environment_crash", evidence, terminal_state,
                )
            if correct_marker_count == goal_marker_count and incorrect_marker_count == 0:
                return V1AttemptResult("success", 1.0, None, None, evidence, terminal_state)
            reason = (
                "invalid_marker_placement" if incorrect_marker_count
                else "no_corner_markers_placed" if correct_marker_count == 0
                else "corner_markers_remaining"
            )
            return V1AttemptResult(
                "partial_completion", correct_marker_count / goal_marker_count,
                "task_failure", reason, evidence, terminal_state,
            )
        clean_house_task: Any = execution_target
        initial_marker_count = int(clean_house_task.initial_number_of_markers)
        remaining_marker_count = int(environment.markers_grid.sum())
        normalized_progress = (initial_marker_count - remaining_marker_count) / initial_marker_count
        evidence = {
            "version": 1,
            "initial_marker_count": initial_marker_count,
            "remaining_marker_count": remaining_marker_count,
            "program_call_count": environment.num_calls,
            "terminal_state": terminal_state,
        }
        if environment.is_crashed():
            return V1AttemptResult(
                "policy_crash",
                normalized_progress,
                "policy_failure",
                "environment_crash",
                evidence,
                terminal_state,
            )
        if remaining_marker_count == 0:
            return V1AttemptResult("success", 1.0, None, None, evidence, terminal_state)
        reason = "no_markers_collected" if normalized_progress == 0 else "markers_remaining"
        return V1AttemptResult(
            "partial_completion",
            normalized_progress,
            "task_failure",
            reason,
            evidence,
            terminal_state,
        )

    def assert_equivalent(
        self,
        task_name: V1TaskName,
        program_source: str,
        seed: int,
        limits: V1ExecutionLimits,
    ) -> None:
        """Reject adapter baseline use unless deterministic V1 facts still agree."""
        adapter_result = self.evaluate(task_name, program_source, seed, limits)
        baseline_result = _evaluate_v1_baseline(task_name, program_source, seed, limits)
        if adapter_result != baseline_result:
            raise ValueError("V1 adapter equivalence failed; baseline selection is blocked")


def _evaluate_v1_baseline(
    task_name: V1TaskName,
    program_source: str,
    seed: int,
    limits: V1ExecutionLimits,
) -> V1ExecutionResult:
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
    return V1ExecutionResult(
        terminal_state=_terminal_state(task_name, environment),
        reward=reward,
        crashed=environment.is_crashed(),
        program_call_count=environment.num_calls,
    )


def _terminal_state(task_name: V1TaskName, environment: Any) -> str:
    if task_name in {"CleanHouse", "FourCorners"}:
        return json.dumps(environment.get_state().tolist(), separators=(",", ":"))
    return json.dumps(
        {
            "agent_dir": int(environment.unwrapped.agent_dir),
            "agent_pos": [int(value) for value in environment.unwrapped.agent_pos],
            "grid": environment.unwrapped.grid.encode().tolist(),
        },
        separators=(",", ":"),
    )
