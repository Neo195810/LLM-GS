from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from prog_policies.base.task import BaseTask
from prog_policies.runtime import create_replay_environment

V1TaskName = Literal["CleanHouse", "RedBlueDoor"]


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
    """A versioned CleanHouse outcome derived from deterministic V1 facts."""

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
        task_name: Literal["CleanHouse"],
        program_source: str,
        seed: int,
        limits: V1ExecutionLimits,
    ) -> V1AttemptResult:
        """Classify one CleanHouse evaluation without changing V1 execution behavior."""
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
        clean_house_task: Any = execution_target
        initial_marker_count = int(clean_house_task.initial_number_of_markers)
        execution_target.evaluate_program(dsl.parse_str_to_node(program_source))
        environment: Any = execution_target.get_environment()
        remaining_marker_count = int(environment.markers_grid.sum())
        normalized_progress = (initial_marker_count - remaining_marker_count) / initial_marker_count
        terminal_state = _terminal_state(task_name, environment)
        evidence: dict[str, object] = {
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


def _terminal_state(task_name: V1TaskName, environment: Any) -> str:
    if task_name == "CleanHouse":
        return json.dumps(environment.get_state().tolist(), separators=(",", ":"))
    return json.dumps(
        {
            "agent_dir": int(environment.unwrapped.agent_dir),
            "agent_pos": [int(value) for value in environment.unwrapped.agent_pos],
            "grid": environment.unwrapped.grid.encode().tolist(),
        },
        separators=(",", ":"),
    )
