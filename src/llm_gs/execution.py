from __future__ import annotations

from typing import Protocol

from llm_gs.contracts import CandidateProgram, EpisodeResult, ExperimentManifest, ExperimentReport
from llm_gs.manifest import CLEAN_HOUSE_PROMPT, OFFLINE_PROMPT
from llm_gs.v1_adapter import V1Adapter, V1ExecutionLimits


class ModelClient(Protocol):
    def propose(self, prompt: str) -> CandidateProgram: ...


class Evaluator(Protocol):
    def evaluate(self, candidate: CandidateProgram, task_seed: int) -> EpisodeResult: ...


class FakeOpenAIClient:
    def propose(self, prompt: str) -> CandidateProgram:
        if prompt == CLEAN_HOUSE_PROMPT:
            return CandidateProgram(source="DEF run m( turnLeft m)")
        if prompt != OFFLINE_PROMPT:
            raise ValueError("fake model received an unknown prompt")
        return CandidateProgram(source="SUCCESS")


class OfflineEchoEvaluator:
    def evaluate(self, candidate: CandidateProgram, task_seed: int) -> EpisodeResult:
        if candidate.source != "SUCCESS":
            raise ValueError("offline evaluator received an invalid candidate")
        _ = task_seed
        return EpisodeResult(outcome="success")


class CleanHouseEvaluator:
    def evaluate(self, candidate: CandidateProgram, task_seed: int) -> EpisodeResult:
        attempt = V1Adapter().evaluate_attempt(
            "CleanHouse", candidate.source, task_seed, V1ExecutionLimits(max_calls=10)
        )
        return EpisodeResult(
            outcome=attempt.outcome,
            normalized_progress=attempt.normalized_progress,
            failure_type=attempt.failure_type,
            failure_reason=attempt.failure_reason,
            evaluation_evidence=attempt.evaluation_evidence,
            terminal_state=attempt.terminal_state,
        )


def execute(
    manifest: ExperimentManifest,
    experiment_id: str,
    execution_id: str,
    model: ModelClient,
    evaluator: Evaluator,
) -> ExperimentReport:
    task_name = manifest.task["name"]
    prompt = CLEAN_HOUSE_PROMPT if task_name == "CleanHouse" else OFFLINE_PROMPT
    candidate = model.propose(prompt)
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
