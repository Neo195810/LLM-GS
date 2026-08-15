from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from prog_policies.karel import KarelDSL

from .ast_utils import dsl_source_to_ast_dict, root_nonterminal_for
from .schemas import SkillRecord
from .skill_manager import JsonSkillStore


def record_skills_from_evaluation(
    evaluation: dict[str, Any],
    store_path: str | Path,
    source_agent: str = "critic",
    created_from: str = "successful_run",
) -> dict[str, Any]:
    """Persist successful plan steps as reusable SkillRecords."""

    critique = evaluation.get("critique", {})
    if not evaluation.get("success") or critique.get("repair_operator") != "store_skill":
        return {
            "stored_skills": 0,
            "updated_skills": 0,
            "skipped_reason": "critique_not_store_skill",
        }

    dsl = KarelDSL()
    store = JsonSkillStore(store_path).load()
    stored_skills = 0
    updated_skills = 0

    for step in evaluation.get("plan", {}).get("steps", []):
        if not step.get("skill_name") or not step.get("dsl_source"):
            continue

        skill_id = _learned_skill_id(evaluation["task"], step)
        existing = store.get(skill_id)
        if existing is None:
            store.upsert(_make_record(evaluation, step, skill_id, dsl, source_agent, created_from))
            stored_skills += 1
        else:
            _merge_observation(existing, evaluation)
            updated_skills += 1

    store.save()
    return {
        "stored_skills": stored_skills,
        "updated_skills": updated_skills,
        "store_path": str(Path(store_path)),
    }


def _make_record(
    evaluation: dict[str, Any],
    step: dict[str, Any],
    skill_id: str,
    dsl: KarelDSL,
    source_agent: str,
    created_from: str,
) -> SkillRecord:
    dsl_source = step["dsl_source"]
    task = evaluation["task"]
    seed = evaluation.get("seed")
    metadata = {
        "source_agent": source_agent,
        "created_from": created_from,
        "source_task": task,
        "source_subgoal": step["subgoal"],
        "source_skill_id": step.get("skill_id"),
        "source_seeds": [] if seed is None else [seed],
    }

    return SkillRecord(
        skill_id=skill_id,
        name=step["skill_name"],
        description=(
            f"Learned from a successful {task} evaluation for subgoal "
            f"{step['subgoal']}."
        ),
        task_family="Karel",
        dsl_source=dsl_source,
        ast_json=dsl_source_to_ast_dict(dsl_source, dsl),
        root_nonterminal=root_nonterminal_for(dsl_source, dsl),
        semantic_tags=_semantic_tags(step),
        success_rate=1.0,
        mean_reward=float(evaluation.get("reward", 0.0)),
        num_evaluations=1,
        metadata=metadata,
    )


def _merge_observation(record: SkillRecord, evaluation: dict[str, Any]) -> None:
    previous_count = record.num_evaluations
    next_count = previous_count + 1
    reward = float(evaluation.get("reward", 0.0))

    record.success_rate = ((record.success_rate * previous_count) + 1.0) / next_count
    record.mean_reward = ((record.mean_reward * previous_count) + reward) / next_count
    record.num_evaluations = next_count

    seed = evaluation.get("seed")
    if seed is not None:
        source_seeds = list(record.metadata.get("source_seeds", []))
        if seed not in source_seeds:
            source_seeds.append(seed)
            source_seeds.sort()
        record.metadata["source_seeds"] = source_seeds


def _learned_skill_id(task: str, step: dict[str, Any]) -> str:
    return ".".join(
        [
            "learned",
            "karel",
            _slug(task),
            _slug(step["subgoal"]),
            _slug(step["skill_name"]),
            "v1",
        ]
    )


def _semantic_tags(step: dict[str, Any]) -> list[str]:
    words = set(_slug(step["subgoal"]).split("_"))
    words.update(_slug(step["skill_name"]).split("_"))
    return sorted(word for word in words if word)


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return cleaned or "unknown"
