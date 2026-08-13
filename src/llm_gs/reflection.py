from __future__ import annotations

from llm_gs.ast_features import normalized_ast_hash
from llm_gs.contracts import CandidateProgram, Diagnosis, EpisodeResult, RepairAttempt, RepairIntent
from llm_gs.proposer import _validate_dsl


class RepeatedRepairError(ValueError):
    """Raised when a repair candidate repeats a previously attempted AST."""


class RepairCycle:
    def __init__(self, maximum_repairs: int = 3) -> None:
        if maximum_repairs < 0:
            raise ValueError("maximum repairs cannot be negative")
        self._maximum_repairs = maximum_repairs

    def diagnose(self, result: EpisodeResult, evidence_index: int) -> Diagnosis:
        if result.evaluation_evidence is None:
            raise ValueError("diagnosis requires episode evaluation evidence")
        reason = result.failure_reason or "unknown failure"
        return Diagnosis(
            evidence_index=evidence_index,
            observation=f"Observed {reason} in episode evidence.",
            hypothesis="The candidate needs a different action sequence to make progress.",
        )

    def repair(
        self,
        parent: CandidateProgram,
        diagnosis: Diagnosis,
        intent: RepairIntent,
        candidate: CandidateProgram,
        repair_round: int,
        seen_ast_hashes: set[str] | None = None,
    ) -> RepairAttempt:
        if repair_round > self._maximum_repairs:
            raise ValueError("repair cycle limit exhausted")
        _validate_dsl(candidate.source)
        candidate_hash = normalized_ast_hash(candidate.source)
        prior_hashes = seen_ast_hashes or {normalized_ast_hash(parent.source)}
        if candidate_hash in prior_hashes:
            raise RepeatedRepairError("repair repeated an attempted AST")
        return RepairAttempt(
            parent_source=parent.source,
            candidate=candidate,
            diagnosis=diagnosis,
            intent=intent,
            normalized_ast_difference=_ast_difference(parent.source, candidate.source),
            round=repair_round,
        )


def _normalized_ast_hash(source: str) -> str:
    return normalized_ast_hash(source)


def _ast_difference(parent: str, child: str) -> str:
    return f"{_normalized_ast_hash(parent)[:12]}->{_normalized_ast_hash(child)[:12]}"
