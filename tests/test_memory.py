from __future__ import annotations

import pytest

from llm_gs.contracts import EpisodeResult, ExperimentSpecification
from llm_gs.manifest import resolve_manifest
from llm_gs.memory import (
    StructuredRetriever,
    curate_clean_house_attempt,
    curate_door_key_attempt,
    curate_four_corners_attempt,
    serialize_memory_context,
    serialize_repair_context,
)
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


def test_repair_context_is_versioned_allowlisted_data_not_historical_instructions() -> None:
    entry = curate_clean_house_attempt("attempt", "DEF run m( move m)", _failure())

    context = serialize_repair_context(_failure(), [entry])

    assert '"version":"memory-context-v1"' in context
    assert '"kind":"post_failure_repair_data"' in context
    assert "DEF run" not in context
    assert "terminal_state" not in context


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


def test_four_corners_memory_retrieval_rejects_clean_house_entries() -> None:
    four_corners_failure = EpisodeResult(
        outcome="partial_completion",
        failure_type="task_failure",
        failure_reason="no_corner_markers_placed",
        evaluation_evidence={
            "goal_marker_count": 4,
            "correct_marker_count": 0,
            "placed_marker_count": 0,
            "incorrect_marker_count": 0,
        },
    )
    four_corners = curate_four_corners_attempt(
        "four-corners", "DEF run m( turnLeft m)", four_corners_failure
    )
    clean_house = curate_clean_house_attempt("clean-house", "DEF run m( move m)", _failure())

    retriever = StructuredRetriever((clean_house, four_corners), task="FourCorners")
    entries, outcome = retriever.retrieve(four_corners_failure, limit=3)

    assert entries == [four_corners]
    assert outcome.candidate_components[clean_house.entry_id].task_compatible is False

    entries, _ = StructuredRetriever((clean_house,), task="FourCorners").retrieve(
        four_corners_failure, limit=3
    )

    assert entries == []


def test_door_key_memory_retrieval_rejects_other_task_entries() -> None:
    result = EpisodeResult(
        outcome="partial_completion",
        failure_type="task_failure",
        failure_reason="key_not_collected",
        evaluation_evidence={
            "initial_key_position": [2, 3],
            "initial_door_position": [4, 3],
            "initial_goal_position": [6, 5],
            "key_collected": False,
            "door_unlocked": False,
            "goal_completed": False,
        },
    )
    door_key = curate_door_key_attempt("door-key", "DEF run m( left m)", result)
    clean_house = curate_clean_house_attempt("clean-house", "DEF run m( move m)", _failure())

    entries, outcome = StructuredRetriever((clean_house, door_key), task="DoorKey").retrieve(
        result
    )

    assert entries == [door_key]
    assert outcome.candidate_components[clean_house.entry_id].task_compatible is False


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


def test_online_memory_lineages_are_isolated_deterministic_and_append_only(tmp_path) -> None:
    starting = curate_clean_house_attempt("starting", "DEF run m( move m)", _failure())
    arm_one_update = curate_clean_house_attempt(
        "arm-one", "DEF run m( turnLeft m)", _failure("stalled")
    )
    arm_two_update = curate_clean_house_attempt(
        "arm-two", "DEF run m( turnRight m)", _failure("blocked")
    )
    store = WorkspaceStore(tmp_path)

    first_lineage = store.fork_memory_lineage(
        "exec_000001", [starting], {"method": "memory_repair", "replicate": 0}
    )
    shared_snapshot_id = store.memory_snapshot_id("exec_000001")
    second_lineage = store.fork_memory_lineage(
        "exec_000002",
        [],
        {"method": "memory_repair", "replicate": 1},
        parent_snapshot_id=shared_snapshot_id,
    )
    rerun_lineage = store.fork_memory_lineage(
        "exec_000003",
        [],
        {"method": "memory_repair", "replicate": 0},
        parent_snapshot_id=shared_snapshot_id,
    )
    store.append_memory_lineage_entries("exec_000001", [arm_one_update])
    store.append_memory_lineage_entries("exec_000002", [arm_two_update])

    assert first_lineage == WorkspaceStore(tmp_path).memory_lineage_id("exec_000001")
    assert first_lineage != second_lineage
    assert first_lineage != rerun_lineage
    assert store.memory_lineage_entries("exec_000001") == [starting, arm_one_update]
    assert store.memory_lineage_entries("exec_000002") == [starting, arm_two_update]
    assert store.memory_lineage_entries("exec_000003") == [starting]
    assert store.memory_lineage_audit("exec_000001") == {
        "lineage_id": first_lineage,
        "parent_snapshot_id": store.memory_snapshot_id("exec_000001"),
        "protocol": "online-v1",
    }


def test_frozen_protocol_arms_must_keep_paired_seed_suites_and_budgets(tmp_path) -> None:
    store = WorkspaceStore(tmp_path)
    first = resolve_manifest(
        ExperimentSpecification.model_validate(
            {
                "display_name": "first",
                "task": {"name": "CleanHouse"},
                "seed_suite": {
                    "memory_training": [1],
                    "development": [2],
                    "held_out": [3],
                },
                "failure_strategy": {"name": "reflect", "max_repair_cycles": 1},
            }
        )
    )
    paired_arm = resolve_manifest(
        ExperimentSpecification.model_validate(
            {
                "display_name": "paired",
                "task": {"name": "CleanHouse"},
                "seed_suite": {
                    "memory_training": [1],
                    "development": [2],
                    "held_out": [3],
                },
                "failure_strategy": {"name": "memory_repair", "max_repair_cycles": 1},
            }
        )
    )
    mismatched_arm = paired_arm.model_copy(
        update={
            "specification": {
                **paired_arm.specification,
                "seed_suite": {
                    "version": 1,
                    "memory_training": [4],
                    "development": [5],
                    "held_out": [6],
                },
            }
        }
    )
    budget_mismatched_arm = paired_arm.model_copy(
        update={
            "budgets": {
                **paired_arm.budgets,
                "episode_evaluations": paired_arm.budgets["episode_evaluations"] + 1,
            }
        }
    )

    store.preregister_paired_protocol(first)
    store.preregister_paired_protocol(paired_arm)
    with pytest.raises(ValueError, match="paired seed suite or budget"):
        store.preregister_paired_protocol(mismatched_arm)
    with pytest.raises(ValueError, match="paired seed suite or budget"):
        store.preregister_paired_protocol(budget_mismatched_arm)
