from __future__ import annotations

import pytest

from llm_gs.contracts import CandidateProgram, EpisodeResult, RepairIntent
from llm_gs.reflection import RepairCycle, RepeatedRepairError


def test_reflection_repair_is_evidence_linked_and_has_parent_provenance() -> None:
    parent = CandidateProgram(source="DEF run m( turnLeft m)")
    result = EpisodeResult(
        outcome="partial_completion",
        normalized_progress=0,
        failure_reason="no_markers_collected",
        evaluation_evidence={"version": 1},
    )
    cycle = RepairCycle()
    diagnosis = cycle.diagnose(result, evidence_index=0)

    repair = cycle.repair(
        parent,
        diagnosis,
        RepairIntent(intended_change="move before turning", preserved_behavior="valid Karel DSL"),
        CandidateProgram(source="DEF run m( move m)"),
        repair_round=1,
    )

    assert repair.parent_source == parent.source
    assert repair.diagnosis.evidence_index == 0
    assert repair.normalized_ast_difference


def test_reflection_stops_repeated_ast_and_exhausted_cycles() -> None:
    cycle = RepairCycle(maximum_repairs=1)
    parent = CandidateProgram(source="DEF run m( turnLeft m)")
    diagnosis = cycle.diagnose(
        EpisodeResult(outcome="partial_completion", evaluation_evidence={"version": 1}), 0
    )
    intent = RepairIntent(intended_change="change", preserved_behavior="valid")

    with pytest.raises(RepeatedRepairError, match="repeated"):
        cycle.repair(parent, diagnosis, intent, parent, repair_round=1)
    with pytest.raises(ValueError, match="exhausted"):
        cycle.repair(parent, diagnosis, intent, CandidateProgram(source="DEF run m( move m)"), 2)
