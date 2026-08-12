from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image

from prog_policies.runtime import create_replay_environment
from prog_policies.utils import get_env_name
from prog_policies.utils.indent import str_to_indent_python


def program_to_python(task: str, dsl_program: str) -> str:
    _, dsl = create_replay_environment(task, 0)
    return str_to_indent_python(dsl_program, dsl)


def render_program_gif(
    task: str,
    dsl_program: str,
    environment_index: int,
    output_dir: str | Path,
    args: dict[str, Any] | None = None,
    max_steps: int = 1000,
) -> Path:
    output_dir = Path(output_dir).resolve()
    digest = hashlib.sha256(
        f"{task}:{environment_index}:{dsl_program}".encode("utf-8")
    ).hexdigest()[:16]
    output_path = output_dir / f"{task}_env-{environment_index}_{digest}.gif"
    if output_path.exists():
        return output_path

    task_env, dsl = create_replay_environment(task, environment_index, args)
    program = dsl.parse_str_to_node(dsl_program)
    if get_env_name(task) == "karel":
        frames = task_env.trace_program(program, max_steps=max_steps, save=False)
    else:
        frames = task_env.trace_program(program, max_steps=max_steps)

    if not frames:
        raise RuntimeError("The program produced no renderable frames.")
    output_dir.mkdir(parents=True, exist_ok=True)
    first, *rest = frames
    first.save(output_path, save_all=True, append_images=rest, duration=120, loop=0)
    return output_path


def load_historical_events(log_path: str | Path) -> list[dict[str, Any]]:
    log_path = Path(log_path)
    content = json.loads(log_path.read_text(encoding="utf-8"))
    args = content.get("args", {})
    task = args.get("task") or log_path.parents[2].name
    seed = int(content.get("seed", args.get("seed", 0)))
    program_record = content.get("program_record", {})
    reward_record = content.get("record", {})
    events = []
    for key, reward in sorted(reward_record.items(), key=lambda item: int(item[0])):
        program_item = program_record.get(str(key), {})
        if isinstance(program_item, dict):
            dsl_program = program_item.get("program", "")
            phase = program_item.get("type", "Historical")
        else:
            dsl_program = str(program_item)
            phase = "Historical"
        if not dsl_program:
            continue
        events.append(
            {
                "schema_version": 1,
                "event": "best_updated",
                "run_id": f"historical:{log_path}",
                "task": task,
                "seed": seed,
                "phase": phase,
                "source_type": phase,
                "program_num": int(key),
                "reward": float(reward),
                "dsl_program": dsl_program,
                "python_program": program_to_python(task, dsl_program),
                "args": args,
            }
        )
    return events
