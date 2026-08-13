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

RETRIEVER_VERSION = "structured-clean-house-v3"
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
        query_progress = _query_progress(self.task, query_evidence)
        components: dict[str, RetrievalCandidateComponents] = {}
        ast_occurrences = {
            entry.normalized_ast_hash: sum(
                other.normalized_ast_hash == entry.normalized_ast_hash for other in self.entries
            )
            for entry in self.entries
        }
        for entry in self.entries:
            entry_progress, improvement = _entry_progress(entry)
            components[entry.entry_id] = RetrievalCandidateComponents(
                task_compatible=entry.task == self.task,
                failure_type_match=entry.failure_type == result.failure_type,
                failure_reason_match=entry.failure_reason == result.failure_reason,
                state_distance=abs(entry_progress - query_progress),
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


def _query_progress(task: str, evidence: dict[str, object]) -> int:
    key = "remaining_marker_count" if task == "CleanHouse" else "correct_marker_count"
    progress = evidence.get(key)
    if not isinstance(progress, int):
        raise ValueError("retrieval requires allowlisted Task evidence")
    return progress


def _entry_progress(entry: MemoryEntry) -> tuple[int, int]:
    if entry.task == "CleanHouse":
        remaining = entry.state_features["remaining_marker_count"]
        return remaining, entry.state_features["initial_marker_count"] - remaining
    correct = entry.state_features["correct_marker_count"]
    return correct, correct


def _integer_evidence(evidence: dict[str, object], field: str) -> int:
    value = evidence.get(field)
    if not isinstance(value, int):
        raise ValueError("memory requires allowlisted FourCorners evidence")
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
    else:
        required = ("goal_marker_count", "correct_marker_count", "incorrect_marker_count")
        if any(not isinstance(evidence.get(field), int) for field in required):
            raise ValueError("repair context requires allowlisted Task evidence")
        current_failure = {
            "failure_type": result.failure_type,
            "failure_reason": result.failure_reason,
            **{field: evidence[field] for field in required},
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
    )
    return {
        "entry_id": entry.entry_id,
        "failure_type": entry.failure_type,
        "failure_reason": entry.failure_reason,
        **{key: entry.evidence[key] for key in keys},
    }


def _evidence_quality(evidence: dict[str, int | str]) -> int:
    return sum(
        (
            isinstance(evidence.get("initial_marker_count"), int),
            isinstance(evidence.get("remaining_marker_count"), int),
            isinstance(evidence.get("failure_reason"), str),
        )
    )
