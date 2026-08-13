from __future__ import annotations

import hashlib
from dataclasses import dataclass

from llm_gs.contracts import (
    EpisodeResult,
    MemoryEntry,
    RetrievalCandidateComponents,
    RetrievalOutcome,
)

RETRIEVER_VERSION = "structured-clean-house-v2"
RETRIEVER_ORDER = (
    "task,failure_type,failure_reason,state_distance,evidence_quality,"
    "improvement,novelty,normalized_ast_hash,entry_id"
)
RETRIEVER_WEIGHTS = "1,1,1,1,1,1,1,1,1"
MEMORY_CONTEXT_LIMIT = 512


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
    normalized_hash = hashlib.sha256(" ".join(source.split()).encode()).hexdigest()
    entry_id = hashlib.sha256(f"{source_attempt_id}:{normalized_hash}".encode()).hexdigest()
    return MemoryEntry(
        entry_id=entry_id,
        task="CleanHouse",
        failure_type=result.failure_type,
        failure_reason=result.failure_reason,
        normalized_ast_hash=normalized_hash,
        state_features={"initial_marker_count": initial, "remaining_marker_count": remaining},
        evidence={"remaining_marker_count": remaining, "failure_reason": result.failure_reason},
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
        for entry in self.entries:
            remaining = entry.state_features["remaining_marker_count"]
            improvement = entry.state_features["initial_marker_count"] - remaining
            components[entry.entry_id] = RetrievalCandidateComponents(
                task_compatible=entry.task == "CleanHouse",
                failure_type_match=entry.failure_type == result.failure_type,
                failure_reason_match=entry.failure_reason == result.failure_reason,
                state_distance=abs(remaining - query_remaining),
                ast_feature=entry.normalized_ast_hash,
                evidence_quality=len(entry.evidence),
                improvement=improvement,
                novelty=1,
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
    context = "\n".join(
        f"failure={entry.failure_reason}; remaining={entry.evidence['remaining_marker_count']}"
        for entry in entries
    )
    if len(context) > MEMORY_CONTEXT_LIMIT:
        raise ValueError("memory context exceeds the configured budget")
    return context
