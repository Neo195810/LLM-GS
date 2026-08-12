from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from prog_policies.karel import KarelDSL
from prog_policies.karel_tasks import get_task_cls as get_karel_task_cls
from prog_policies.minigrid.dsl import MinigridDSL
from prog_policies.minigrid_tasks import get_task_cls as get_minigrid_task_cls
from prog_policies.utils import get_env_name


def _value(args: Any, name: str, default: Any) -> Any:
    if isinstance(args, dict):
        return args.get(name, default)
    return getattr(args, name, default)


def build_karel_env_args(args: Any) -> dict[str, Any]:
    task = _value(args, "task", "DoorKey")
    env_args = {
        "env_height": 8,
        "env_width": 8,
        "crashable": _value(args, "crashable", False),
        "leaps_behaviour": True,
        "max_calls": 10000,
    }

    if task in {"StairClimber", "StairClimberSparse", "TopOff", "FourCorners"}:
        env_args["env_height"] = 12
        env_args["env_width"] = 12
    elif task == "CleanHouse":
        env_args["env_height"] = 14
        env_args["env_width"] = 22
    elif task == "WallAvoider":
        env_args["env_height"] = 8
        env_args["env_width"] = 5

    return env_args


def create_task_envs(args: Any, num_envs: int | None = None):
    task = _value(args, "task", "DoorKey")
    count = num_envs if num_envs is not None else _value(args, "num_envs", 32)

    if get_env_name(task) == "karel":
        dsl = KarelDSL()
        task_cls = get_karel_task_cls(task)
        env_args = build_karel_env_args(args)
        task_envs = [task_cls(env_args, seed) for seed in range(count)]
    else:
        dsl = MinigridDSL()
        task_cls = get_minigrid_task_cls(task)
        task_envs = [
            task_cls(
                seed,
                _value(args, "crashable", False),
                _value(args, "crash_penalty", 0.0),
                _value(args, "max_calls", 1000),
            )
            for seed in range(count)
        ]

    return task_envs, dsl


def create_replay_environment(task: str, environment_index: int, args: dict[str, Any] | None = None):
    replay_args = dict(args or {})
    replay_args["task"] = task
    task_envs, dsl = create_task_envs(SimpleNamespace(**replay_args), num_envs=environment_index + 1)
    return task_envs[environment_index], dsl
