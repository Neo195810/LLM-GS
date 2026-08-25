from __future__ import annotations

from llm_gs.contracts import CandidateProgram, EpisodeResult
from llm_gs.execution import _candidate_admission_audit


def test_candidate_admission_audit_aggregates_failure_reasons() -> None:
    audit = _candidate_admission_audit(
        [
            (
                CandidateProgram(source="DEF run m( left m)"),
                [
                    EpisodeResult(
                        outcome="policy_crash",
                        failure_type="policy_failure",
                        failure_reason="call_limit_exhausted",
                    ),
                    EpisodeResult(
                        outcome="policy_crash",
                        failure_type="policy_failure",
                        failure_reason="stalled_policy",
                    ),
                    EpisodeResult(
                        outcome="partial_completion",
                        failure_type="task_failure",
                        failure_reason="goal_not_reached",
                    ),
                ],
            )
        ]
    )

    assert audit["candidates"] == [
        {
            "outcomes": {"policy_crash": 2, "partial_completion": 1},
            "failure_reasons": {
                "call_limit_exhausted": 1,
                "stalled_policy": 1,
                "goal_not_reached": 1,
            },
            "mean_normalized_progress": 1.0,
            "admitted": False,
        }
    ]
    assert audit["failure_reasons"] == {
        "call_limit_exhausted": 1,
        "stalled_policy": 1,
        "goal_not_reached": 1,
    }
