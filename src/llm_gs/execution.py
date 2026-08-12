from __future__ import annotations

from typing import Protocol

from llm_gs.contracts import CandidateProgram, EpisodeResult, ExperimentManifest, ExperimentReport
from llm_gs.manifest import OFFLINE_PROMPT


class ModelClient(Protocol):
    def propose(self, prompt: str) -> CandidateProgram: ...


class Evaluator(Protocol):
    def evaluate(self, candidate: CandidateProgram, task_seed: int) -> EpisodeResult: ...


class FakeOpenAIClient:
    def propose(self, prompt: str) -> CandidateProgram:
        if prompt != OFFLINE_PROMPT:
            raise ValueError("fake model received an unknown prompt")
        return CandidateProgram(source="SUCCESS")


class OfflineEchoEvaluator:
    def evaluate(self, candidate: CandidateProgram, task_seed: int) -> EpisodeResult:
        if candidate.source != "SUCCESS":
            raise ValueError("offline evaluator received an invalid candidate")
        _ = task_seed
        return EpisodeResult(outcome="success")


def execute(
    manifest: ExperimentManifest,
    experiment_id: str,
    execution_id: str,
    model: ModelClient,
    evaluator: Evaluator,
) -> ExperimentReport:
    candidate = model.propose(OFFLINE_PROMPT)
    task_seeds = manifest.specification["seeds"]
    if not isinstance(task_seeds, dict) or not isinstance(task_seeds.get("task"), list):
        raise ValueError("resolved manifest contains invalid task seeds")
    result = evaluator.evaluate(candidate, int(task_seeds["task"][0]))
    return ExperimentReport(
        experiment_id=experiment_id,
        execution_id=execution_id,
        candidate_programs=1,
        episode_evaluations=result.episode_evaluations,
        model_requests=candidate.model_requests,
        outcomes={result.outcome: 1},
    )
