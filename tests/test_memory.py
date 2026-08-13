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

    entries, outcome = StructuredRetriever((first, second)).retrieve(_failure(), limit=1)

    assert [entry.entry_id for entry in entries] == outcome.selected_entry_ids
    assert set(outcome.candidate_components) == {first.entry_id, second.entry_id}
    assert sum("selected" in codes for codes in outcome.reason_codes.values()) == 1
    assert sum("not_selected" in codes for codes in outcome.reason_codes.values()) == 1
    assert "terminal_state" not in serialize_memory_context(entries)


def test_retrieval_scores_observable_features_and_has_a_stable_tiebreaker() -> None:
    closest = curate_clean_house_attempt("closest", "DEF run m( move m)", _failure())
    farther = curate_clean_house_attempt(
        "farther",
        "DEF run m( turnLeft m)",
        EpisodeResult(
            outcome="partial_completion",
            failure_type="task_failure",
            failure_reason="no_markers_collected",
            evaluation_evidence={"initial_marker_count": 11, "remaining_marker_count": 8},
        ),
    )

    first, first_outcome = StructuredRetriever((farther, closest)).retrieve(_failure(), limit=2)
    second, second_outcome = StructuredRetriever((closest, farther)).retrieve(_failure(), limit=2)

    assert [entry.entry_id for entry in first] == [closest.entry_id, farther.entry_id]
    assert [entry.entry_id for entry in second] == [closest.entry_id, farther.entry_id]
    assert first_outcome == second_outcome
    assert first_outcome.candidate_components[closest.entry_id].evidence_quality == 3
    assert first_outcome.candidate_components[closest.entry_id].improvement == 0
    assert first_outcome.candidate_components[closest.entry_id].novelty == 1


def test_memory_provenance_survives_store_restart(tmp_path) -> None:
    entry = curate_clean_house_attempt("attempt-1", "DEF run m( turnLeft m)", _failure())
    store = WorkspaceStore(tmp_path)
    store.save_memory_entry(entry)

    assert WorkspaceStore(tmp_path).memory_entries() == [entry]


def test_memory_snapshot_is_read_only_and_excludes_current_execution_entries(tmp_path) -> None:
    prior = curate_clean_house_attempt("prior", "DEF run m( move m)", _failure())
    current = curate_clean_house_attempt("current", "DEF run m( turnLeft m)", _failure())
    store = WorkspaceStore(tmp_path)
    store.save_memory_entry(prior)

    assert store.freeze_memory_snapshot("exec_000001") == [prior]
    snapshot_id = store.memory_snapshot_id("exec_000001")
    store.save_memory_entry(current)

    assert store.memory_snapshot_entries("exec_000001") == [prior]
    assert store.freeze_memory_snapshot("exec_000001") == [prior]
    assert store.memory_snapshot_id("exec_000001") == snapshot_id
