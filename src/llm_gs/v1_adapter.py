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
