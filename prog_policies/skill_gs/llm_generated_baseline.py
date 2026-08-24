from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from prog_policies.karel_tasks import DoorKey

from .doorkey_policy import ACTION_NAMES
from .doorkey_state import extract_doorkey_state
from .evaluator import KAREL_DOORKEY_ENV_ARGS
from .skill_manager import JsonSkillStore


GenerateResponse = Callable[[str, str, float], str]

ACTION_SCHEMA_NAMES = ["move", "turnLeft", "turnRight", "pickMarker", "putMarker"]
DIRECTION_NAMES = {
    0: "north",
    1: "east",
    2: "south",
    3: "west",
}
DIRECTION_TOKENS = {
    0: "A^",
    1: "A>",
    2: "Av",
    3: "A<",
}
ENVIRONMENT_STATE_PLACEHOLDER = "{{environment_state}}"
SKILLS_CONTEXT_PLACEHOLDER = "{{skills_context}}"
NO_SKILLS_CONTEXT = "No learned skills are available yet."


def parse_policy_response(raw_response: str) -> dict[str, Any]:
    """Parse the structured JSON action-sequence policy returned by an LLM."""

    try:
        payload = json.loads(raw_response.strip())
    except json.JSONDecodeError as exc:
        raise ValueError("LLM response is not valid JSON.") from exc

    if not isinstance(payload, dict):
        raise ValueError("LLM response must be a JSON object.")
    if payload.get("policy_type") != "action_sequence":
        raise ValueError("policy_type must be 'action_sequence'.")

    actions = payload.get("actions")
    if not isinstance(actions, list):
        raise ValueError("actions must be a list.")
    invalid_actions = [
        action
        for action in actions
        if not isinstance(action, str) or action not in ACTION_NAMES
    ]
    if invalid_actions:
        raise ValueError(
            "actions contains unsupported action(s): "
            + ", ".join(str(action) for action in invalid_actions)
        )

    return {
        "policy_name": str(payload.get("policy_name", "")),
        "policy_type": payload["policy_type"],
        "actions": actions,
        "notes": str(payload.get("notes", "")),
    }


def run_llm_generated_one_shot_smoke(
    prompt_template_path: str | Path,
    model_name: str,
    seed: int = 0,
    temperature: float = 0.0,
    cache_dir: str | Path = "output/skill_gs/llm_generated_baseline",
    skill_store_path: str | Path | None = None,
    provider: str = "Ollama",
    num_gpu: int | None = None,
    think: bool | str | None = False,
    num_predict: int | None = None,
    reasoning_effort: str | None = None,
    max_output_tokens: int | None = None,
    generate_response: GenerateResponse | None = None,
) -> dict[str, Any]:
    """Run one LLM-generated action sequence against one DoorKey seed."""

    prompt_path = Path(prompt_template_path)
    prompt_template = prompt_path.read_text(encoding="utf-8")
    environment_status = extract_initial_doorkey_environment_status(seed)
    skills_context = build_skills_context(
        skill_store_path,
        environment_status=environment_status,
    )
    prompt = build_state_conditioned_prompt(
        prompt_template,
        environment_status,
        skills_context=skills_context,
    )
    if generate_response:
        raw_response = generate_response(prompt, model_name, temperature)
    elif provider.lower() == "openai":
        raw_response = generate_openai_response(
            prompt,
            model_name,
            temperature,
            reasoning_effort=reasoning_effort,
            max_output_tokens=max_output_tokens,
        )
    elif provider.lower() == "gemini":
        raw_response = generate_gemini_response(
            prompt,
            model_name,
            temperature,
            max_output_tokens=max_output_tokens,
        )
    elif provider.lower() == "ollama":
        raw_response = generate_ollama_response(
            prompt,
            model_name,
            temperature,
            num_gpu=num_gpu,
            think=think,
            num_predict=num_predict,
        )
    else:
        raise ValueError(
            f"Unsupported LLM provider: {provider}. Expected OpenAI, Gemini, or Ollama."
        )
    policy = parse_policy_response(raw_response)
    evaluation = evaluate_doorkey_action_sequence(
        seed=seed,
        actions=policy["actions"],
    )
    result = {
        "task": "DoorKey",
        "provider": provider,
        "model_name": model_name,
        "temperature": temperature,
        "num_gpu": num_gpu,
        "think": think,
        "num_predict": num_predict,
        "reasoning_effort": reasoning_effort,
        "max_output_tokens": max_output_tokens,
        "prompt_template_path": str(prompt_path),
        "skill_store_path": str(Path(skill_store_path)) if skill_store_path else None,
        "output_format": "structured_json",
        "cache_response": True,
        "seed": seed,
        "environment_status": environment_status,
        "skills_context": skills_context,
        "final_prompt": prompt,
        "raw_response": raw_response,
        "policy": policy,
        "evaluation": evaluation,
    }
    cache_paths = _write_cache(result, cache_dir, prompt_path, model_name, seed)
    result.update({key: str(path) for key, path in cache_paths.items()})
    return result


def extract_initial_doorkey_environment_status(seed: int) -> dict[str, Any]:
    """Build a prompt-ready DoorKey initial state snapshot for one seed."""

    task = DoorKey(dict(KAREL_DOORKEY_ENV_ARGS), seed)
    env = task.get_environment()
    snapshot = extract_doorkey_state(env)
    _, height, width = env.state_shape
    hero_row, hero_col, hero_dir = snapshot.agent
    door_cells = [list(cell) for cell in getattr(task, "door_cells", [])]

    return {
        "task": "DoorKey",
        "seed": seed,
        "grid_size": [int(height), int(width)],
        "coordinate_system": "zero_indexed_row_col",
        "agent": {
            "position": [hero_row, hero_col],
            "direction": DIRECTION_NAMES[hero_dir],
            "direction_index": hero_dir,
        },
        "key_position": list(snapshot.key_cell) if snapshot.key_cell else None,
        "goal_position": list(snapshot.goal_cell) if snapshot.goal_cell else None,
        "door_cells": door_cells,
        "wall_column": snapshot.wall_column,
        "door_open": snapshot.door_open,
        "wall_cells": _wall_cells(env),
        "ascii_map": _ascii_map(env, door_cells),
    }


def build_state_conditioned_prompt(
    template: str,
    environment_status: dict[str, Any],
    skills_context: str | None = None,
) -> str:
    """Insert a runtime environment snapshot into a static prompt template."""

    environment_text = _format_environment_status(environment_status)
    skills_text = skills_context if skills_context is not None else NO_SKILLS_CONTEXT
    if ENVIRONMENT_STATE_PLACEHOLDER in template:
        prompt = template.replace(ENVIRONMENT_STATE_PLACEHOLDER, environment_text)
    else:
        prompt = template.rstrip() + "\n\n" + environment_text

    if SKILLS_CONTEXT_PLACEHOLDER in prompt:
        return prompt.replace(SKILLS_CONTEXT_PLACEHOLDER, skills_text)
    if skills_context and skills_context != NO_SKILLS_CONTEXT:
        return prompt.rstrip() + "\n\nAvailable Skills:\n" + skills_text
    return prompt


def build_skills_context(
    skill_store_path: str | Path | None,
    task_family: str = "Karel",
    max_skills: int = 5,
    environment_status: dict[str, Any] | None = None,
) -> str:
    """Format learned skills as concise prompt context for an LLM policy."""

    if not skill_store_path:
        return NO_SKILLS_CONTEXT

    store_path = Path(skill_store_path)
    if not store_path.exists():
        return NO_SKILLS_CONTEXT

    store = JsonSkillStore(store_path).load()
    stage_tags = _stage_tags(environment_status)
    records = []
    for record in store.all():
        if task_family and record.task_family.lower() != task_family.lower():
            continue
        if not _skill_matches_stage(record, stage_tags):
            continue
        records.append(record)
    if not records:
        return NO_SKILLS_CONTEXT

    records.sort(
        key=lambda record: (
            -record.success_rate,
            -record.mean_reward,
            -record.num_evaluations,
            record.complexity,
            record.skill_id,
        )
    )

    return "\n\n".join(
        _format_skill_for_prompt(index, record)
        for index, record in enumerate(records[:max_skills], 1)
    )


def generate_openai_response(
    prompt: str,
    model_name: str,
    temperature: float,
    reasoning_effort: str | None = None,
    max_output_tokens: int | None = None,
    api_key: str | None = None,
) -> str:
    """Generate one OpenAI Responses API result with strict JSON requested."""

    resolved_api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not resolved_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    payload = build_openai_responses_payload(
        prompt=prompt,
        model_name=model_name,
        temperature=temperature,
        reasoning_effort=reasoning_effort,
        max_output_tokens=max_output_tokens,
    )
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {resolved_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"OpenAI API request failed with HTTP {exc.code}: {error_body[:500]}"
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("OpenAI API request failed.") from exc
    return extract_openai_response_text(body)


def generate_gemini_response(
    prompt: str,
    model_name: str,
    temperature: float,
    max_output_tokens: int | None = None,
    api_key: str | None = None,
) -> str:
    """Generate one Gemini Interactions API result with JSON schema output."""

    resolved_api_key = (
        api_key
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
    )
    if not resolved_api_key:
        raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY is not set.")
    payload = build_gemini_interactions_payload(
        prompt=prompt,
        model_name=model_name,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )
    request = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-goog-api-key": resolved_api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Gemini API request failed with HTTP {exc.code}: {error_body[:500]}"
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("Gemini API request failed.") from exc
    return extract_gemini_response_text(body)


def build_openai_responses_payload(
    prompt: str,
    model_name: str,
    temperature: float,
    reasoning_effort: str | None = None,
    max_output_tokens: int | None = None,
) -> dict[str, Any]:
    """Build the OpenAI Responses API payload for the DoorKey JSON policy."""

    schema = _action_sequence_policy_schema()
    payload: dict[str, Any] = {
        "model": model_name,
        "input": prompt,
        "temperature": temperature,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "doorkey_action_sequence_policy",
                "strict": True,
                "schema": schema,
            },
        },
    }
    if reasoning_effort is not None:
        payload["reasoning"] = {"effort": reasoning_effort}
    if max_output_tokens is not None:
        payload["max_output_tokens"] = max_output_tokens
    return payload


def build_gemini_interactions_payload(
    prompt: str,
    model_name: str,
    temperature: float,
    max_output_tokens: int | None = None,
) -> dict[str, Any]:
    """Build the Gemini Interactions API payload for the DoorKey JSON policy."""

    generation_config: dict[str, Any] = {
        "temperature": temperature,
        "thinking_level": "minimal",
    }
    if max_output_tokens is not None:
        generation_config["max_output_tokens"] = max_output_tokens
    return {
        "model": model_name,
        "input": prompt,
        "generation_config": generation_config,
        "response_format": {
            "type": "text",
            "mime_type": "application/json",
            "schema": _action_sequence_policy_schema(),
        },
    }


def extract_openai_response_text(body: dict[str, Any]) -> str:
    """Extract output text from an OpenAI Responses API JSON body."""

    output_text = body.get("output_text")
    if isinstance(output_text, str) and output_text:
        return output_text

    for output_item in body.get("output", []):
        if not isinstance(output_item, dict):
            continue
        for content_item in output_item.get("content", []):
            if not isinstance(content_item, dict):
                continue
            text = content_item.get("text")
            if isinstance(text, str) and text:
                return text

    raise ValueError("OpenAI response did not contain output text.")


def extract_gemini_response_text(body: dict[str, Any]) -> str:
    """Extract text from a Gemini Interactions API response body."""

    output_text = body.get("output_text")
    if isinstance(output_text, str) and output_text:
        return output_text

    if body.get("policy_type") == "action_sequence":
        return json.dumps(body)

    for step in reversed(body.get("steps", [])):
        if not isinstance(step, dict) or step.get("type") != "model_output":
            continue
        texts = []
        for content_item in step.get("content", []):
            if not isinstance(content_item, dict):
                continue
            if content_item.get("type") != "text":
                continue
            text = content_item.get("text")
            if isinstance(text, str) and text:
                texts.append(text)
        if texts:
            return "".join(texts)

    raise ValueError("Gemini response did not contain output text.")


def generate_ollama_response(
    prompt: str,
    model_name: str,
    temperature: float,
    num_gpu: int | None = None,
    think: bool | str | None = False,
    num_predict: int | None = None,
) -> str:
    """Generate one non-streamed Ollama response with JSON formatting requested."""

    payload = build_ollama_generate_payload(
        prompt=prompt,
        model_name=model_name,
        temperature=temperature,
        num_gpu=num_gpu,
        think=think,
        num_predict=num_predict,
    )
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("Ollama API request failed.") from exc
    return str(body.get("response", ""))


def build_ollama_generate_payload(
    prompt: str,
    model_name: str,
    temperature: float,
    num_gpu: int | None = None,
    think: bool | str | None = False,
    num_predict: int | None = None,
) -> dict[str, Any]:
    options: dict[str, Any] = {"temperature": temperature}
    if num_gpu is not None:
        options["num_gpu"] = num_gpu
    if num_predict is not None:
        options["num_predict"] = num_predict
    payload: dict[str, Any] = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": options,
    }
    if think is not None:
        payload["think"] = think
    return payload


def evaluate_doorkey_action_sequence(
    seed: int,
    actions: list[str],
) -> dict[str, Any]:
    """Execute a fixed action sequence in the repo-native Karel DoorKey task."""

    task = DoorKey(dict(KAREL_DOORKEY_ENV_ARGS), seed)
    env = task.get_environment()
    trace = []
    total_reward = 0.0
    terminated = False

    for step_index, action in enumerate(actions):
        if action not in ACTION_NAMES:
            raise ValueError(f"Unsupported DoorKey action: {action}")
        before = extract_doorkey_state(env)
        env.run_action(action)
        terminated, instant_reward = task.get_reward(env)
        total_reward += instant_reward
        after = extract_doorkey_state(env)
        trace.append(
            {
                "step": step_index + 1,
                "action": action,
                "instant_reward": instant_reward,
                "total_reward": total_reward,
                "agent_before": before.agent,
                "agent_after": after.agent,
                "door_open": after.door_open,
            }
        )
        if terminated or env.is_crashed():
            break

    return {
        "task": "DoorKey",
        "seed": seed,
        "success": bool(terminated and not env.is_crashed() and total_reward >= 1.0),
        "reward": total_reward,
        "steps": len(trace),
        "terminated": terminated,
        "crashed": env.is_crashed(),
        "trace": trace,
    }


def _write_cache(
    result: dict[str, Any],
    cache_dir: str | Path,
    prompt_path: Path,
    model_name: str,
    seed: int,
) -> dict[str, Path]:
    cache_root = Path(cache_dir)
    cache_root.mkdir(parents=True, exist_ok=True)
    prefix = f"{prompt_path.stem}_seed{seed}_{_sanitize_model_name(model_name)}"
    cache_path = cache_root / f"{prefix}.json"
    state_path = cache_root / f"{prefix}_state.json"
    prompt_cache_path = cache_root / f"{prefix}_prompt.txt"
    cache_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    state_path.write_text(
        json.dumps(result["environment_status"], indent=2),
        encoding="utf-8",
    )
    prompt_cache_path.write_text(result["final_prompt"], encoding="utf-8")
    return {
        "cache_path": cache_path,
        "state_cache_path": state_path,
        "prompt_cache_path": prompt_cache_path,
    }


def _sanitize_model_name(model_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", model_name)


def _action_sequence_policy_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "policy_name": {"type": "string"},
            "policy_type": {
                "type": "string",
                "enum": ["action_sequence"],
            },
            "actions": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ACTION_SCHEMA_NAMES,
                },
            },
            "notes": {"type": "string"},
        },
        "required": [
            "policy_name",
            "policy_type",
            "actions",
            "notes",
        ],
    }


def _format_environment_status(status: dict[str, Any]) -> str:
    agent = status["agent"]
    return "\n".join(
        [
            "Current Environment State:",
            f"task: {status['task']}",
            f"seed: {status['seed']}",
            f"grid_size: {status['grid_size']}",
            f"coordinate_system: {status['coordinate_system']}",
            f"agent_position: {agent['position']}",
            f"agent_direction: {agent['direction']}",
            f"key_position: {status['key_position']}",
            f"door_cells: {status['door_cells']}",
            f"door_open: {status['door_open']}",
            f"goal_position: {status['goal_position']}",
            f"wall_column: {status['wall_column']}",
            f"wall_cells: {status['wall_cells']}",
            "ascii_map:",
            status["ascii_map"],
        ]
    )


def _format_skill_for_prompt(index: int, record) -> str:
    return "\n".join(
        [
            f"Skill {index}:",
            f"Skill ID: {record.skill_id}",
            f"Name: {record.name}",
            f"Purpose: {record.description}",
            f"Semantic Tags: {_format_list(record.semantic_tags)}",
            f"Preconditions: {_format_list(record.preconditions)}",
            f"Postconditions: {_format_list(record.postconditions)}",
            f"Action Pattern: {record.dsl_source}",
            (
                "Reliability: "
                f"success_rate={record.success_rate:.3f}, "
                f"mean_reward={record.mean_reward:.3f}, "
                f"evaluations={record.num_evaluations}"
            ),
        ]
    )


def _stage_tags(environment_status: dict[str, Any] | None) -> set[str] | None:
    if environment_status is None:
        return None
    if environment_status.get("door_open"):
        return {"door_open", "key_picked"}
    return {"door_closed", "key_not_picked"}


def _skill_matches_stage(record, stage_tags: set[str] | None) -> bool:
    if stage_tags is None:
        return True
    preconditions = set(record.preconditions)
    if not preconditions:
        return True
    return preconditions.issubset(stage_tags)


def _format_list(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def _wall_cells(env) -> list[list[int]]:
    _, height, width = env.state_shape
    return [
        [int(row), int(col)]
        for row in range(height)
        for col in range(width)
        if env.state[4, row, col]
    ]


def _ascii_map(env, door_cells: list[list[int]]) -> str:
    _, height, width = env.state_shape
    hero_row, hero_col, hero_dir = env.get_hero_pos()
    door_cell_set = {tuple(cell) for cell in door_cells}
    key_goal_state = extract_doorkey_state(env)
    key_cell = key_goal_state.key_cell
    goal_cell = key_goal_state.goal_cell
    rows = []

    for row in range(height):
        tokens = []
        for col in range(width):
            cell = (row, col)
            if cell == (hero_row, hero_col):
                tokens.append(DIRECTION_TOKENS[int(hero_dir)])
            elif cell == key_cell:
                tokens.append("K")
            elif cell == goal_cell:
                tokens.append("G")
            elif cell in door_cell_set:
                tokens.append("D" if env.state[4, row, col] else "d")
            elif env.state[4, row, col]:
                tokens.append("#")
            elif env.markers_grid[row, col] > 0:
                tokens.append("M")
            else:
                tokens.append(".")
        rows.append(" ".join(tokens))
    return "\n".join(rows)
