from __future__ import annotations

import hashlib

from llm_gs.contracts import CandidateProgram, Diagnosis, EpisodeResult, RepairAttempt, RepairIntent
from llm_gs.proposer import _validate_dsl


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
        source: str,
        round: int,
    ) -> RepairAttempt:
        if round > self._maximum_repairs:
            raise ValueError("repair cycle limit exhausted")
        _validate_dsl(source)
        if _normalized_ast_hash(source) == _normalized_ast_hash(parent.source):
            raise ValueError("repair repeated the parent AST")
        return RepairAttempt(
            parent_source=parent.source,
            candidate=CandidateProgram(source=source),
            diagnosis=diagnosis,
            intent=intent,
            normalized_ast_difference=_ast_difference(parent.source, source),
            round=round,
        )


def _normalized_ast_hash(source: str) -> str:
    return hashlib.sha256(" ".join(source.split()).encode()).hexdigest()


def _ast_difference(parent: str, child: str) -> str:
    return f"{_normalized_ast_hash(parent)[:12]}->{_normalized_ast_hash(child)[:12]}"
