from __future__ import annotations

import json
from pathlib import Path

from .ast_utils import dsl_source_to_ast_dict, root_nonterminal_for
from .schemas import RetrievedSkill, SkillQuery, SkillRecord


class JsonSkillStore:
    """Small JSON-backed skill DB.

    The first version is intentionally simple so teammates can replace the
    storage backend with SQLite or vector search without changing callers.
    """

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self._records: dict[str, SkillRecord] = {}

    def load(self) -> "JsonSkillStore":
        if not self.path or not self.path.exists():
            return self
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self._records = {
            item["skill_id"]: SkillRecord.from_dict(item) for item in data.get("skills", [])
        }
        return self

    def save(self) -> None:
        if not self.path:
            raise ValueError("Cannot save a skill store without a path.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"skills": [record.to_dict() for record in self._records.values()]}
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def upsert(self, skill: SkillRecord) -> None:
        self._records[skill.skill_id] = skill

    def get(self, skill_id: str) -> SkillRecord | None:
        return self._records.get(skill_id)

    def extend(self, skills: list[SkillRecord]) -> None:
        for skill in skills:
            self.upsert(skill)

    def all(self) -> list[SkillRecord]:
        return list(self._records.values())


class SkillManager:
    """Retrieve compatible AST skills for planner subgoals."""

    def __init__(self, store: JsonSkillStore):
        self.store = store

    def retrieve(self, query: SkillQuery) -> list[RetrievedSkill]:
        results: list[RetrievedSkill] = []
        context = set(query.context_tags)
        required = set(query.required_preconditions)
        query_terms = _terms([query.task, query.subgoal, *query.context_tags])

        for skill in self.store.all():
            if query.root_nonterminal and skill.root_nonterminal != query.root_nonterminal:
                continue
            if required and not required.issubset(context):
                continue
            if skill.preconditions and not set(skill.preconditions).issubset(context):
                continue

            score, reasons = _score_skill(skill, query_terms, query)
            if score > 0:
                results.append(RetrievedSkill(skill=skill, score=score, reasons=reasons))

        results.sort(key=lambda item: item.score, reverse=True)
        return results[: query.top_k]


def make_default_minigrid_skills(dsl) -> list[SkillRecord]:
    """Seed skills for the first Skill-GS smoke run."""

    specs = [
        {
            "skill_id": "minigrid.navigate_forward_until_blocked.v1",
            "name": "navigate_forward_until_blocked",
            "description": "Move forward until the front cell is blocked.",
            "task_family": "MiniGrid",
            "dsl_source": "WHILE c( front_is_clear c) w( forward w)",
            "semantic_tags": ["navigation", "move", "forward", "explore"],
            "postconditions": ["position_changed"],
            "success_rate": 0.75,
            "mean_reward": 0.25,
        },
        {
            "skill_id": "minigrid.pickup_object.v1",
            "name": "pickup_object",
            "description": "Pick up the object at the current cell.",
            "task_family": "MiniGrid",
            "dsl_source": "pickup",
            "semantic_tags": ["pickup", "object", "ball", "key"],
            "preconditions": ["object_at_agent"],
            "postconditions": ["is_carrying_object"],
            "success_rate": 0.9,
            "mean_reward": 0.5,
        },
        {
            "skill_id": "minigrid.open_front_door.v1",
            "name": "open_front_door",
            "description": "Toggle a door when a door is directly in front.",
            "task_family": "MiniGrid",
            "dsl_source": "IF c( front_object_type h( door h) c) i( toggle i)",
            "semantic_tags": ["door", "toggle", "open"],
            "preconditions": ["door_in_front"],
            "postconditions": ["door_open"],
            "success_rate": 0.85,
            "mean_reward": 0.4,
        },
        {
            "skill_id": "minigrid.drop_object.v1",
            "name": "drop_object",
            "description": "Drop the carried object at the current cell.",
            "task_family": "MiniGrid",
            "dsl_source": "drop",
            "semantic_tags": ["drop", "object", "putnear"],
            "preconditions": ["is_carrying_object"],
            "postconditions": ["object_dropped"],
            "success_rate": 0.85,
            "mean_reward": 0.5,
        },
        {
            "skill_id": "minigrid.avoid_lava_left_probe.v1",
            "name": "avoid_lava_left_probe",
            "description": "Turn left when lava is directly in front.",
            "task_family": "MiniGrid",
            "dsl_source": "IF c( front_object_type h( lava h) c) i( left i)",
            "semantic_tags": ["lava", "avoid", "navigation"],
            "preconditions": ["lava_in_front"],
            "postconditions": ["changed_heading"],
            "success_rate": 0.7,
            "mean_reward": 0.2,
        },
    ]

    records: list[SkillRecord] = []
    for spec in specs:
        dsl_source = spec["dsl_source"]
        records.append(
            SkillRecord(
                ast_json=dsl_source_to_ast_dict(dsl_source, dsl),
                root_nonterminal=root_nonterminal_for(dsl_source, dsl),
                num_evaluations=1,
                failure_signatures=[],
                **spec,
            )
        )
    return records


def make_default_karel_doorkey_skills(dsl) -> list[SkillRecord]:
    """Seed Karel DoorKey skills for the MVP execution loop."""

    specs = [
        {
            "skill_id": "karel.doorkey.navigate_forward_until_blocked.v1",
            "name": "navigate_forward_until_blocked",
            "description": "Move through a clear corridor until the front cell is blocked.",
            "task_family": "Karel",
            "dsl_source": "WHILE c( frontIsClear c) w( move w)",
            "semantic_tags": ["navigation", "move", "explore", "corridor"],
            "postconditions": ["position_changed"],
            "success_rate": 0.75,
            "mean_reward": 0.25,
        },
        {
            "skill_id": "karel.doorkey.turn_left.v1",
            "name": "turn_left",
            "description": "Rotate left to change heading.",
            "task_family": "Karel",
            "dsl_source": "turnLeft",
            "semantic_tags": ["navigation", "turn", "left"],
            "postconditions": ["changed_heading"],
            "success_rate": 0.95,
            "mean_reward": 0.0,
        },
        {
            "skill_id": "karel.doorkey.turn_right.v1",
            "name": "turn_right",
            "description": "Rotate right to change heading.",
            "task_family": "Karel",
            "dsl_source": "turnRight",
            "semantic_tags": ["navigation", "turn", "right"],
            "postconditions": ["changed_heading"],
            "success_rate": 0.95,
            "mean_reward": 0.0,
        },
        {
            "skill_id": "karel.doorkey.pick_marker.v1",
            "name": "pick_marker",
            "description": "Pick up the marker used as the DoorKey key.",
            "task_family": "Karel",
            "dsl_source": "pickMarker",
            "semantic_tags": ["pickup", "marker", "key"],
            "preconditions": ["marker_present"],
            "postconditions": ["door_open", "no_marker_at_agent"],
            "success_rate": 0.9,
            "mean_reward": 0.5,
        },
        {
            "skill_id": "karel.doorkey.unlock_door_with_key.v1",
            "name": "unlock_door_with_key",
            "description": "Pick up the DoorKey key marker, which unlocks the divider door.",
            "task_family": "Karel",
            "dsl_source": "pickMarker",
            "semantic_tags": ["door", "open", "unlock", "key", "marker"],
            "postconditions": ["door_open"],
            "success_rate": 0.9,
            "mean_reward": 0.5,
        },
        {
            "skill_id": "karel.doorkey.put_marker.v1",
            "name": "put_marker",
            "description": "Place a marker on the DoorKey goal marker.",
            "task_family": "Karel",
            "dsl_source": "putMarker",
            "semantic_tags": ["put", "drop", "marker", "goal"],
            "preconditions": ["goal_cell"],
            "postconditions": ["goal_topped_off"],
            "success_rate": 0.9,
            "mean_reward": 0.5,
        },
    ]

    records: list[SkillRecord] = []
    for spec in specs:
        dsl_source = spec["dsl_source"]
        records.append(
            SkillRecord(
                ast_json=dsl_source_to_ast_dict(dsl_source, dsl),
                root_nonterminal=root_nonterminal_for(dsl_source, dsl),
                num_evaluations=1,
                failure_signatures=[],
                **spec,
            )
        )
    return records


def _score_skill(
    skill: SkillRecord, query_terms: set[str], query: SkillQuery
) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0
    normalized_subgoal = query.subgoal.replace("_", " ").lower()
    skill_terms = _terms(
        [
            skill.name,
            skill.description,
            skill.task_family,
            *skill.semantic_tags,
            *skill.postconditions,
        ]
    )

    overlap = len(query_terms & skill_terms)
    if overlap:
        score += overlap * 2.0
        reasons.append(f"term_overlap={overlap}")

    strong_tags = {"navigation", "pickup", "drop", "door", "toggle", "lava", "avoid"}
    navigation_subgoal = any(
        word in normalized_subgoal for word in ("locate", "navigate", "cross")
    )
    exact_tag_hits = []
    for tag in skill.semantic_tags:
        if tag not in strong_tags:
            continue
        if navigation_subgoal and tag in {"door", "toggle"}:
            continue
        if tag.replace("_", " ").lower() in normalized_subgoal:
            exact_tag_hits.append(tag)
    if navigation_subgoal and "navigation" in skill.semantic_tags:
        exact_tag_hits.append("navigation")
    if exact_tag_hits:
        score += len(exact_tag_hits) * 3.0
        reasons.append("subgoal_tag=" + ",".join(exact_tag_hits))

    if query.task.lower() in skill.task_family.lower() or skill.task_family.lower() in {
        "minigrid",
        "karel",
    }:
        score += 1.0
        reasons.append("task_family")

    if query.failure_signature and query.failure_signature in skill.failure_signatures:
        score += 2.0
        reasons.append("known_failure_signature")

    if skill.success_rate:
        score += skill.success_rate
        reasons.append(f"success_rate={skill.success_rate:.2f}")
    if skill.mean_reward:
        score += skill.mean_reward * 0.5
        reasons.append(f"mean_reward={skill.mean_reward:.2f}")

    score -= min(skill.complexity, 30) * 0.01
    return score, reasons


def _terms(values: list[str]) -> set[str]:
    terms: set[str] = set()
    for value in values:
        cleaned = (
            value.replace("_", " ")
            .replace("-", " ")
            .replace(".", " ")
            .replace("/", " ")
            .lower()
        )
        terms.update(part for part in cleaned.split() if part)
    return terms
