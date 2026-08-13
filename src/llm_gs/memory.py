from __future__ import annotations

import hashlib
from dataclasses import dataclass

from llm_gs.contracts import EpisodeResult, MemoryEntry, RetrievalOutcome

RETRIEVER_VERSION = "structured-clean-house-v1"
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
        ranked = sorted(
            self.entries,
            key=lambda entry: (
                entry.task != "CleanHouse",
                entry.failure_type != result.failure_type,
                entry.failure_reason != result.failure_reason,
                entry.normalized_ast_hash,
                entry.entry_id,
            ),
        )[:limit]
        reason_codes = {
            entry.entry_id: ["task_compatible", "failure_type_rank", "failure_reason_rank"]
            for entry in ranked
        }
        return ranked, RetrievalOutcome(
            query_failure_type=result.failure_type,
            query_failure_reason=result.failure_reason,
            selected_entry_ids=[entry.entry_id for entry in ranked],
            reason_codes=reason_codes,
        )


def serialize_memory_context(entries: list[MemoryEntry]) -> str:
    context = "\n".join(
        f"failure={entry.failure_reason}; remaining={entry.evidence['remaining_marker_count']}"
        for entry in entries
    )
    if len(context) > MEMORY_CONTEXT_LIMIT:
        raise ValueError("memory context exceeds the configured budget")
    return context
