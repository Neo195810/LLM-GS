from __future__ import annotations

from llm_gs.contracts import EpisodeResult
from llm_gs.memory import StructuredRetriever, curate_clean_house_attempt, serialize_memory_context
from llm_gs.storage import WorkspaceStore


def _failure(reason: str = "no_markers_collected") -> EpisodeResult:
    return EpisodeResult(
        outcome="partial_completion",
        failure_type="task_failure",
        failure_reason=reason,
        evaluation_evidence={"initial_marker_count": 11, "remaining_marker_count": 11},
    )


def test_memory_curator_and_retriever_are_deterministic_and_allowlisted() -> None:
    first = curate_clean_house_attempt("attempt-2", "DEF run m( turnLeft m)", _failure())
    second = curate_clean_house_attempt("attempt-1", "DEF run m( move m)", _failure())

    entries, outcome = StructuredRetriever((first, second)).retrieve(_failure())

    assert [entry.entry_id for entry in entries] == outcome.selected_entry_ids
    assert all("task_compatible" in codes for codes in outcome.reason_codes.values())
    assert "terminal_state" not in serialize_memory_context(entries)


def test_memory_provenance_survives_store_restart(tmp_path) -> None:
    entry = curate_clean_house_attempt("attempt-1", "DEF run m( turnLeft m)", _failure())
    store = WorkspaceStore(tmp_path)
    store.save_memory_entry(entry)

    assert WorkspaceStore(tmp_path).memory_entries() == [entry]
