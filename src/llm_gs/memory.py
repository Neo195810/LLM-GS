from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from llm_gs.ast_features import normalized_ast_hash
from llm_gs.contracts import (
    EpisodeResult,
    MemoryEntry,
    RetrievalCandidateComponents,
    RetrievalOutcome,
)

RETRIEVER_VERSION = "structured-task-v4"
RETRIEVER_ORDER = (
    "task,failure_type,failure_reason,state_distance,evidence_quality,"
    "improvement,novelty,normalized_ast_hash,entry_id"
)
RETRIEVER_WEIGHTS = "1,1,1,1,1,1,1,1,1"
MEMORY_CONTEXT_LIMIT = 2048
MEMORY_CONTEXT_SERIALIZER_VERSION = "memory-context-v1"
_MEMORY_ENTRY_FIELDS = (
    "entry_id",
    "failure_type",
    "failure_reason",
    "initial_marker_count",
    "remaining_marker_count",
)


def curate_clean_house_attempt(
    source_attempt_id: str, source: str, result: EpisodeResult
) -> MemoryEntry:
    if result.failure_type is None or result.failure_reason is None:
        raise ValueError("only failed attempts can become CleanHouse memory")
    evidence = result.evaluation_evidence or {}
    remaining = evidence.get("remaining_marker_count")
    initial = evidence.get("initial_marker_count")
    if not isinstance(remaining, int) or not isinstance(initial, int):
        raise ValueError("memory requires allowlisted marker-count evidence")
    normalized_hash = normalized_ast_hash(source)
    entry_id = hashlib.sha256(f"{source_attempt_id}:{normalized_hash}".encode()).hexdigest()
    return MemoryEntry(
        entry_id=entry_id,
        task="CleanHouse",
        failure_type=result.failure_type,
        failure_reason=result.failure_reason,
        normalized_ast_hash=normalized_hash,
        state_features={"initial_marker_count": initial, "remaining_marker_count": remaining},
        evidence={
            "initial_marker_count": initial,
            "remaining_marker_count": remaining,
            "failure_reason": result.failure_reason,
        },
        source_attempt_id=source_attempt_id,
    )


def curate_four_corners_attempt(
    source_attempt_id: str, source: str, result: EpisodeResult
) -> MemoryEntry:
    if result.failure_type is None or result.failure_reason is None:
        raise ValueError("only failed attempts can become FourCorners memory")
    evidence = result.evaluation_evidence or {}
    goal_marker_count = _integer_evidence(evidence, "goal_marker_count")
    correct_marker_count = _integer_evidence(evidence, "correct_marker_count")
    incorrect_marker_count = _integer_evidence(evidence, "incorrect_marker_count")
    normalized_hash = normalized_ast_hash(source)
    entry_id = hashlib.sha256(f"{source_attempt_id}:{normalized_hash}".encode()).hexdigest()
    return MemoryEntry(
        entry_id=entry_id,
        task="FourCorners",
        failure_type=result.failure_type,
        failure_reason=result.failure_reason,
        normalized_ast_hash=normalized_hash,
        state_features={
            "goal_marker_count": goal_marker_count,
            "correct_marker_count": correct_marker_count,
            "incorrect_marker_count": incorrect_marker_count,
        },
        evidence={
            "goal_marker_count": goal_marker_count,
            "correct_marker_count": correct_marker_count,
            "incorrect_marker_count": incorrect_marker_count,
            "failure_reason": result.failure_reason,
        },
        source_attempt_id=source_attempt_id,
    )


def curate_door_key_attempt(
    source_attempt_id: str, source: str, result: EpisodeResult
) -> MemoryEntry:
    if result.failure_type is None or result.failure_reason is None:
        raise ValueError("only failed attempts can become DoorKey memory")
    evidence = result.evaluation_evidence or {}
    key_position = _position_evidence(evidence, "initial_key_position")
    door_position = _position_evidence(evidence, "initial_door_position")
    goal_position = _position_evidence(evidence, "initial_goal_position")
    if key_position is None or door_position is None or goal_position is None:
        raise ValueError("memory requires allowlisted DoorKey state features")
    normalized_hash = normalized_ast_hash(source)
    entry_id = hashlib.sha256(f"{source_attempt_id}:{normalized_hash}".encode()).hexdigest()
    state_features = _door_key_features(key_position, door_position, goal_position)
    return MemoryEntry(
        entry_id=entry_id,
        task="DoorKey",
        failure_type=result.failure_type,
        failure_reason=result.failure_reason,
        normalized_ast_hash=normalized_hash,
        state_features=state_features,
        evidence={
            "failure_reason": result.failure_reason,
            **state_features,
            "key_collected": int(evidence.get("key_collected") is True),
            "door_unlocked": int(evidence.get("door_unlocked") is True),
            "goal_completed": int(evidence.get("goal_completed") is True),
        },
        source_attempt_id=source_attempt_id,
    )


def curate_red_blue_door_attempt(
    source_attempt_id: str, source: str, result: EpisodeResult
) -> MemoryEntry:
    if result.failure_type is None or result.failure_reason is None:
        raise ValueError("only failed attempts can become RedBlueDoor memory")
    evidence = result.evaluation_evidence or {}
    red_position = _position_evidence(evidence, "initial_red_door_position")
    blue_position = _position_evidence(evidence, "initial_blue_door_position")
    if red_position is None or blue_position is None:
        raise ValueError("memory requires allowlisted RedBlueDoor state features")
    normalized_hash = normalized_ast_hash(source, "RedBlueDoor")
    entry_id = hashlib.sha256(f"{source_attempt_id}:{normalized_hash}".encode()).hexdigest()
    state_features = _red_blue_door_features(red_position, blue_position)
    return MemoryEntry(
        entry_id=entry_id,
        task="RedBlueDoor",
        failure_type=result.failure_type,
        failure_reason=result.failure_reason,
        normalized_ast_hash=normalized_hash,
        state_features=state_features,
        evidence={
            "failure_reason": result.failure_reason,
            **state_features,
            "red_door_opened": _boolean_evidence(evidence, "red_door_opened"),
            "blue_door_opened": _boolean_evidence(evidence, "blue_door_opened"),
            "red_opened_before_blue": _boolean_evidence(evidence, "red_opened_before_blue"),
        },
        source_attempt_id=source_attempt_id,
    )


@dataclass(frozen=True)
class StructuredRetriever:
    entries: tuple[MemoryEntry, ...]
    task: str = "CleanHouse"
    version: str = RETRIEVER_VERSION

    def retrieve(
        self, result: EpisodeResult, limit: int = 3
    ) -> tuple[list[MemoryEntry], RetrievalOutcome]:
        if result.failure_type is None or result.failure_reason is None:
            raise ValueError("retrieval requires a classified failure")
        query_evidence = result.evaluation_evidence or {}
        query_features = _query_features(self.task, query_evidence)
        components: dict[str, RetrievalCandidateComponents] = {}
        ast_occurrences = {
            entry.normalized_ast_hash: sum(
                other.normalized_ast_hash == entry.normalized_ast_hash for other in self.entries
            )
            for entry in self.entries
        }
        for entry in self.entries:
            entry_features, improvement = _entry_features(entry)
            task_compatible = entry.task == self.task
            components[entry.entry_id] = RetrievalCandidateComponents(
                task_compatible=task_compatible,
                failure_type_match=entry.failure_type == result.failure_type,
                failure_reason_match=entry.failure_reason == result.failure_reason,
                state_distance=(
                    _state_distance(query_features, entry_features) if task_compatible else 0
                ),
                ast_feature=entry.normalized_ast_hash,
                evidence_quality=_evidence_quality(entry.evidence),
                improvement=improvement,
                novelty=1 if ast_occurrences[entry.normalized_ast_hash] == 1 else 0,
            )
        compatible_entries = [entry for entry in self.entries if entry.task == self.task]
        ranked = sorted(
            compatible_entries,
            key=lambda entry: (
                not components[entry.entry_id].failure_type_match,
                not components[entry.entry_id].failure_reason_match,
                components[entry.entry_id].state_distance,
                -components[entry.entry_id].evidence_quality,
                -components[entry.entry_id].improvement,
                -components[entry.entry_id].novelty,
                components[entry.entry_id].ast_feature,
                entry.entry_id,
            ),
        )
        selected = ranked[:limit]
        selected_ids = {entry.entry_id for entry in selected}
        reason_codes = {
            entry.entry_id: [
                "selected" if entry.entry_id in selected_ids else "not_selected",
                "task_compatible"
                if components[entry.entry_id].task_compatible
                else "task_incompatible",
                "failure_type_match"
                if components[entry.entry_id].failure_type_match
                else "failure_type_mismatch",
                "failure_reason_match"
                if components[entry.entry_id].failure_reason_match
                else "failure_reason_mismatch",
            ]
            for entry in ranked
        }
        for entry in self.entries:
            if entry.task != self.task:
                reason_codes[entry.entry_id] = ["not_selected", "task_incompatible"]
        return selected, RetrievalOutcome(
            query_failure_type=result.failure_type,
            query_failure_reason=result.failure_reason,
            selected_entry_ids=[entry.entry_id for entry in selected],
            reason_codes=reason_codes,
            candidate_components=components,
        )


def _query_features(task: str, evidence: dict[str, object]) -> tuple[int, ...]:
    if task == "CleanHouse":
        return (_integer_evidence(evidence, "remaining_marker_count"),)
    if task == "FourCorners":
        return (_integer_evidence(evidence, "correct_marker_count"),)
    if task == "DoorKey":
        positions = (
            _position_evidence(evidence, "initial_key_position"),
            _position_evidence(evidence, "initial_door_position"),
            _position_evidence(evidence, "initial_goal_position"),
        )
        if any(position is None for position in positions):
            raise ValueError("retrieval requires allowlisted DoorKey evidence")
        key_position, door_position, goal_position = positions
        assert key_position is not None
        assert door_position is not None
        assert goal_position is not None
        return (*key_position, *door_position, *goal_position)
    if task == "RedBlueDoor":
        red_position = _position_evidence(evidence, "initial_red_door_position")
        blue_position = _position_evidence(evidence, "initial_blue_door_position")
        if red_position is None or blue_position is None:
            raise ValueError("retrieval requires allowlisted RedBlueDoor evidence")
        return (*red_position, *blue_position)
    raise ValueError(f"Task {task} does not support Structured Retrieval")


def _entry_features(entry: MemoryEntry) -> tuple[tuple[int, ...], int]:
    if entry.task == "CleanHouse":
        remaining = entry.state_features["remaining_marker_count"]
        return (remaining,), entry.state_features["initial_marker_count"] - remaining
    if entry.task == "FourCorners":
        correct = entry.state_features["correct_marker_count"]
        return (correct,), correct
    if entry.task == "DoorKey":
        return (
            tuple(entry.state_features[key] for key in _DOOR_KEY_FEATURE_KEYS),
            sum(
                _memory_int(entry.evidence, field)
                for field in ("key_collected", "door_unlocked", "goal_completed")
            ),
        )
    if entry.task == "RedBlueDoor":
        return (
            tuple(entry.state_features[key] for key in _RED_BLUE_DOOR_FEATURE_KEYS),
            sum(
                _memory_int(entry.evidence, field)
                for field in (
                    "red_door_opened",
                    "blue_door_opened",
                    "red_opened_before_blue",
                )
            ),
        )
    raise ValueError(f"Task {entry.task} does not support Structured Retrieval")


def _state_distance(query: tuple[int, ...], entry: tuple[int, ...]) -> int:
    if len(query) != len(entry):
        raise ValueError("retrieval state feature dimensions must match")
    return sum(abs(current - prior) for current, prior in zip(query, entry, strict=True))


def _position_evidence(evidence: dict[str, object], field: str) -> tuple[int, int] | None:
    value = evidence.get(field)
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(isinstance(coordinate, int) for coordinate in value)
    ):
        return None
    return int(value[0]), int(value[1])


_DOOR_KEY_FEATURE_KEYS = (
    "key_column",
    "key_row",
    "door_column",
    "door_row",
    "goal_column",
    "goal_row",
)


def _door_key_features(
    key_position: tuple[int, int], door_position: tuple[int, int], goal_position: tuple[int, int]
) -> dict[str, int]:
    values = (*key_position, *door_position, *goal_position)
    return dict(zip(_DOOR_KEY_FEATURE_KEYS, values, strict=True))


_RED_BLUE_DOOR_FEATURE_KEYS = (
    "red_door_column",
    "red_door_row",
    "blue_door_column",
    "blue_door_row",
)


def _red_blue_door_features(
    red_position: tuple[int, int], blue_position: tuple[int, int]
) -> dict[str, int]:
    return dict(zip(_RED_BLUE_DOOR_FEATURE_KEYS, (*red_position, *blue_position), strict=True))


def _query_progress(task: str, evidence: dict[str, object]) -> int:
    """Compatibility helper retained for callers that report scalar progress."""
    features = _query_features(task, evidence)
    if len(features) != 1:
        raise ValueError("retrieval requires allowlisted Task evidence")
    return features[0]


def _integer_evidence(evidence: dict[str, object], field: str) -> int:
    value = evidence.get(field)
    if not isinstance(value, int):
        raise ValueError("memory requires allowlisted FourCorners evidence")
    return value


def _boolean_evidence(evidence: dict[str, object], field: str) -> int:
    value = evidence.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"memory requires boolean {field} evidence")
    return int(value)


def _memory_int(evidence: dict[str, int | str], field: str) -> int:
    value = evidence[field]
    if not isinstance(value, int):
        raise ValueError("memory requires integer evidence")
    return value


def serialize_memory_context(entries: list[MemoryEntry]) -> str:
    """Serialize retrieved facts as data, never as instructions from prior attempts."""
    context = json.dumps(
        {
            "version": MEMORY_CONTEXT_SERIALIZER_VERSION,
            "kind": "retrieved_experience_data",
            "entries": [_serialized_entry(entry) for entry in entries],
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(context) > MEMORY_CONTEXT_LIMIT:
        raise ValueError("memory context exceeds the configured budget")
    return context


def serialize_repair_context(result: EpisodeResult, entries: list[MemoryEntry]) -> str:
    """Combine allowlisted current evidence and retrieved facts for a repair request."""
    evidence = result.evaluation_evidence or {}
    if "initial_marker_count" in evidence:
        current_failure = {
            "failure_type": result.failure_type,
            "failure_reason": result.failure_reason,
            "initial_marker_count": evidence.get("initial_marker_count"),
            "remaining_marker_count": evidence.get("remaining_marker_count"),
        }
    elif "goal_marker_count" in evidence:
        required = ("goal_marker_count", "correct_marker_count", "incorrect_marker_count")
        if any(not isinstance(evidence.get(field), int) for field in required):
            raise ValueError("repair context requires allowlisted Task evidence")
        current_failure = {
            "failure_type": result.failure_type,
            "failure_reason": result.failure_reason,
            **{field: evidence[field] for field in required},
        }
    elif "initial_key_position" in evidence:
        positions = {
            field: _position_evidence(evidence, field)
            for field in (
                "initial_key_position",
                "initial_door_position",
                "initial_goal_position",
            )
        }
        if any(position is None for position in positions.values()):
            raise ValueError("repair context requires allowlisted DoorKey evidence")
        key_position = positions["initial_key_position"]
        door_position = positions["initial_door_position"]
        goal_position = positions["initial_goal_position"]
        assert key_position is not None and door_position is not None and goal_position is not None
        current_failure = {
            "failure_type": result.failure_type,
            "failure_reason": result.failure_reason,
            **_door_key_features(key_position, door_position, goal_position),
            "key_collected": int(evidence.get("key_collected") is True),
            "door_unlocked": int(evidence.get("door_unlocked") is True),
            "goal_completed": int(evidence.get("goal_completed") is True),
        }
    else:
        red_position = _position_evidence(evidence, "initial_red_door_position")
        blue_position = _position_evidence(evidence, "initial_blue_door_position")
        if red_position is None or blue_position is None:
            raise ValueError("repair context requires allowlisted RedBlueDoor evidence")
        current_failure = {
            "failure_type": result.failure_type,
            "failure_reason": result.failure_reason,
            **_red_blue_door_features(red_position, blue_position),
            "red_door_opened": _boolean_evidence(evidence, "red_door_opened"),
            "blue_door_opened": _boolean_evidence(evidence, "blue_door_opened"),
            "red_opened_before_blue": _boolean_evidence(evidence, "red_opened_before_blue"),
        }
    retrieved = json.loads(serialize_memory_context(entries))
    context = json.dumps(
        {
            "version": MEMORY_CONTEXT_SERIALIZER_VERSION,
            "kind": "post_failure_repair_data",
            "current_failure": current_failure,
            "retrieved_memory": retrieved["entries"],
            "entry_fields": _MEMORY_ENTRY_FIELDS,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(context) > MEMORY_CONTEXT_LIMIT:
        raise ValueError("repair context exceeds the configured budget")
    return context


def _serialized_entry(entry: MemoryEntry) -> dict[str, int | str]:
    keys = (
        ("initial_marker_count", "remaining_marker_count")
        if entry.task == "CleanHouse"
        else ("goal_marker_count", "correct_marker_count", "incorrect_marker_count")
        if entry.task == "FourCorners"
        else (*_DOOR_KEY_FEATURE_KEYS, "key_collected", "door_unlocked", "goal_completed")
        if entry.task == "DoorKey"
        else (
            *_RED_BLUE_DOOR_FEATURE_KEYS,
            "red_door_opened",
            "blue_door_opened",
            "red_opened_before_blue",
        )
    )
    return {
        "entry_id": entry.entry_id,
        "failure_type": entry.failure_type,
        "failure_reason": entry.failure_reason,
        **{key: entry.evidence[key] for key in keys},
    }


def _evidence_quality(evidence: dict[str, int | str]) -> int:
    return sum(isinstance(value, (int, str)) for value in evidence.values())
