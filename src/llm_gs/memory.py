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


@dataclass(frozen=True)
class StructuredRetriever:
    entries: tuple[MemoryEntry, ...]
    version: str = RETRIEVER_VERSION

    def retrieve(
        self, result: EpisodeResult, limit: int = 3
    ) -> tuple[list[MemoryEntry], RetrievalOutcome]:
        if result.failure_type is None or result.failure_reason is None:
            raise ValueError("retrieval requires a classified failure")
        query_evidence = result.evaluation_evidence or {}
        query_remaining = query_evidence.get("remaining_marker_count")
        if not isinstance(query_remaining, int):
            raise ValueError("retrieval requires allowlisted marker-count evidence")
        components: dict[str, RetrievalCandidateComponents] = {}
        ast_occurrences = {
            entry.normalized_ast_hash: sum(
                other.normalized_ast_hash == entry.normalized_ast_hash for other in self.entries
            )
            for entry in self.entries
        }
        for entry in self.entries:
            remaining = entry.state_features["remaining_marker_count"]
            improvement = entry.state_features["initial_marker_count"] - remaining
            components[entry.entry_id] = RetrievalCandidateComponents(
                task_compatible=entry.task == "CleanHouse",
                failure_type_match=entry.failure_type == result.failure_type,
                failure_reason_match=entry.failure_reason == result.failure_reason,
                state_distance=abs(remaining - query_remaining),
                ast_feature=entry.normalized_ast_hash,
                evidence_quality=_evidence_quality(entry.evidence),
                improvement=improvement,
                novelty=1 if ast_occurrences[entry.normalized_ast_hash] == 1 else 0,
            )
        ranked = sorted(
            self.entries,
            key=lambda entry: (
                not components[entry.entry_id].task_compatible,
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
        return selected, RetrievalOutcome(
            query_failure_type=result.failure_type,
            query_failure_reason=result.failure_reason,
            selected_entry_ids=[entry.entry_id for entry in selected],
            reason_codes=reason_codes,
            candidate_components=components,
        )


def serialize_memory_context(entries: list[MemoryEntry]) -> str:
    """Serialize retrieved facts as data, never as instructions from prior attempts."""
    context = json.dumps(
        {
            "version": MEMORY_CONTEXT_SERIALIZER_VERSION,
            "kind": "retrieved_experience_data",
            "entries": [
                {
                    "entry_id": entry.entry_id,
                    "failure_type": entry.failure_type,
                    "failure_reason": entry.failure_reason,
                    "initial_marker_count": entry.evidence["initial_marker_count"],
                    "remaining_marker_count": entry.evidence["remaining_marker_count"],
                }
                for entry in entries
            ],
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
    initial = evidence.get("initial_marker_count")
    remaining = evidence.get("remaining_marker_count")
    if not isinstance(initial, int) or not isinstance(remaining, int):
        raise ValueError("repair context requires allowlisted marker-count evidence")
    retrieved = json.loads(serialize_memory_context(entries))
    context = json.dumps(
        {
            "version": MEMORY_CONTEXT_SERIALIZER_VERSION,
            "kind": "post_failure_repair_data",
            "current_failure": {
                "failure_type": result.failure_type,
                "failure_reason": result.failure_reason,
                "initial_marker_count": initial,
                "remaining_marker_count": remaining,
            },
            "retrieved_memory": retrieved["entries"],
            "entry_fields": _MEMORY_ENTRY_FIELDS,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(context) > MEMORY_CONTEXT_LIMIT:
        raise ValueError("repair context exceeds the configured budget")
    return context


def _evidence_quality(evidence: dict[str, int | str]) -> int:
    return sum(
        (
            isinstance(evidence.get("initial_marker_count"), int),
            isinstance(evidence.get("remaining_marker_count"), int),
            isinstance(evidence.get("failure_reason"), str),
        )
    )
