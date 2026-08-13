from __future__ import annotations

from typing import Protocol, runtime_checkable

from llm_gs.contracts import (
    CandidateProgram,
    EpisodeResult,
    EvaluationEvidence,
    ExperimentManifest,
    ExperimentReport,
    RepairIntent,
)
from llm_gs.manifest import CLEAN_HOUSE_PROMPT, OFFLINE_PROMPT
from llm_gs.reflection import RepairCycle
from llm_gs.storage import PendingWork, WorkspaceStore
from llm_gs.v1_adapter import V1Adapter, V1ExecutionLimits


class ModelClient(Protocol):
    def propose(self, prompt: str) -> CandidateProgram: ...


class Evaluator(Protocol):
    def evaluate(self, candidate: CandidateProgram, task_seed: int) -> EpisodeResult: ...


@runtime_checkable
class Repairer(Protocol):
    def repair(self, prompt: str) -> CandidateProgram: ...


class FakeOpenAIClient:
    def propose(self, prompt: str) -> CandidateProgram:
        if prompt.startswith("Repair CleanHouse"):
            return CandidateProgram(source="DEF run m( move m)")
        if prompt == CLEAN_HOUSE_PROMPT:
            return CandidateProgram(source="DEF run m( turnLeft m)")
        if prompt != OFFLINE_PROMPT:
            raise ValueError("fake model received an unknown prompt")
        return CandidateProgram(source="SUCCESS")

    def repair(self, prompt: str) -> CandidateProgram:
        return self.propose(prompt)


def reflect_once(
    parent: CandidateProgram,
    result: EpisodeResult,
    repairer: Repairer,
    cycle: RepairCycle,
    execution_id: str,
    store: WorkspaceStore,
) -> CandidateProgram:
    diagnosis = cycle.diagnose(result, evidence_index=0)
    intent = RepairIntent(
        intended_change="replace the stalled action sequence",
        preserved_behavior="a complete valid Karel DSL program",
    )
    candidate = repairer.repair(f"Repair CleanHouse using: {diagnosis.observation}")
    repair = cycle.repair(parent, diagnosis, intent, candidate.source, round=1)
    store.save_repair_attempt(execution_id, repair)
    return repair.candidate


class OfflineEchoEvaluator:
    def evaluate(self, candidate: CandidateProgram, task_seed: int) -> EpisodeResult:
        if candidate.source != "SUCCESS":
            raise ValueError("offline evaluator received an invalid candidate")
        _ = task_seed
        return EpisodeResult(outcome="success")


class CleanHouseEvaluator:
    def evaluate(self, candidate: CandidateProgram, task_seed: int) -> EpisodeResult:
        adapter = V1Adapter()
        limits = V1ExecutionLimits(max_calls=10)
        adapter.assert_equivalent("CleanHouse", candidate.source, task_seed, limits)
        attempt = adapter.evaluate_attempt("CleanHouse", candidate.source, task_seed, limits)
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
    results = [evaluator.evaluate(candidate, int(seed)) for seed in task_seeds["task"]]
    if (
        manifest.failure_strategy["name"] == "reflect"
        and results[0].outcome != "success"
        and isinstance(model, Repairer)
    ):
        cycle = RepairCycle(int(manifest.failure_strategy["max_repair_cycles"]))
        diagnosis = cycle.diagnose(results[0], evidence_index=0)
        repair_source = model.repair(f"Repair CleanHouse using: {diagnosis.observation}")
        repair = cycle.repair(
            candidate,
            diagnosis,
            RepairIntent(
                intended_change="replace the stalled action sequence",
                preserved_behavior="a complete valid Karel DSL program",
            ),
            repair_source.source,
            round=1,
        )
        candidate = repair.candidate
        results = [evaluator.evaluate(candidate, int(seed)) for seed in task_seeds["task"]]
    outcomes: dict[str, int] = {}
    evidence: list[EvaluationEvidence] = []
    for result in results:
        outcomes[result.outcome] = outcomes.get(result.outcome, 0) + 1
        if result.evaluation_evidence is not None:
            evidence.append(
                EvaluationEvidence(
                    outcome=result.outcome,
                    normalized_progress=result.normalized_progress,
                    failure_type=result.failure_type,
                    failure_reason=result.failure_reason,
                    evidence=result.evaluation_evidence,
                    terminal_state=result.terminal_state,
                )
            )
    return ExperimentReport(
        experiment_id=experiment_id,
        execution_id=execution_id,
        candidate_programs=candidate.model_requests,
        episode_evaluations=sum(result.episode_evaluations for result in results),
        model_requests=candidate.model_requests,
        outcomes=outcomes,
        evaluation_evidence=evidence,
    )


def execute_resumable(
    manifest: ExperimentManifest,
    experiment_id: str,
    store: WorkspaceStore,
    model: ModelClient,
    evaluator: Evaluator,
    stop_after: int | None = None,
) -> tuple[ExperimentReport | None, str]:
    if manifest.failure_strategy["name"] == "reflect":
        return _execute_reflect(manifest, experiment_id, store, model, evaluator)
    work = store.next_pending_work(experiment_id)
    if work is None and store.active_execution_id(experiment_id) is None:
        new_execution_id = store.next_execution_id(experiment_id)
        prompt = CLEAN_HOUSE_PROMPT if manifest.task["name"] == "CleanHouse" else OFFLINE_PROMPT
        candidate = model.propose(prompt)
        store.begin_execution_for_experiment(
            manifest, experiment_id, new_execution_id, candidate.source, candidate.model_requests
        )
        records = getattr(model, "records", None)
        if isinstance(records, list):
            store.save_model_request_records(new_execution_id, records)
        work = store.next_pending_work(experiment_id)
    completed = 0
    while work is not None:
        result = evaluator.evaluate(CandidateProgram(source=work.candidate_source), work.seed)
        store.complete_work(work, result.model_dump_json())
        completed += 1
        if stop_after is not None and completed >= stop_after:
            return None, "interrupted"
        work = store.next_pending_work(experiment_id)
    active_execution_id = store.active_execution_id(experiment_id)
    if active_execution_id is None:
        raise ValueError("no running execution is available to resume")
    rows = store.completed_episode_results(active_execution_id)
    if not rows:
        raise ValueError("no execution work is available to resume")
    results = [EpisodeResult.model_validate_json(row) for row in rows]
    report = _report_from_results(
        experiment_id, active_execution_id, results, store.model_requests(active_execution_id)
    )
    store.save(manifest, report)
    return report, "completed"


def _execute_reflect(
    manifest: ExperimentManifest,
    experiment_id: str,
    store: WorkspaceStore,
    model: ModelClient,
    evaluator: Evaluator,
) -> tuple[ExperimentReport, str]:
    if not isinstance(model, Repairer):
        raise ValueError("reflect strategy requires a repair-capable model")
    execution_id = store.next_execution_id(experiment_id)
    candidate = model.propose(CLEAN_HOUSE_PROMPT)
    store.begin_execution_for_experiment(
        manifest, experiment_id, execution_id, candidate.source, candidate.model_requests
    )
    seed = _task_seeds(manifest)[0]
    initial_result = evaluator.evaluate(candidate, seed)
    store.complete_work(
        PendingWork(execution_id, seed, candidate.source, candidate.model_requests),
        initial_result.model_dump_json(),
    )
    final_candidate = candidate
    final_result = initial_result
    if initial_result.outcome != "success":
        final_candidate = reflect_once(
            candidate,
            initial_result,
            model,
            RepairCycle(int(manifest.failure_strategy["max_repair_cycles"])),
            execution_id,
            store,
        )
        final_result = evaluator.evaluate(final_candidate, seed)
    report = _report_from_results(
        experiment_id,
        execution_id,
        [initial_result, final_result] if final_candidate != candidate else [initial_result],
        candidate.model_requests + final_candidate.model_requests,
        candidate_programs=2 if final_candidate != candidate else 1,
    )
    store.save(manifest, report)
    return report, "completed"


def _task_seeds(manifest: ExperimentManifest) -> list[int]:
    seeds = manifest.specification["seeds"]
    if not isinstance(seeds, dict) or not isinstance(seeds.get("task"), list):
        raise ValueError("resolved manifest contains invalid task seeds")
    return [int(seed) for seed in seeds["task"]]


def _report_from_results(
    experiment_id: str,
    execution_id: str,
    results: list[EpisodeResult],
    model_requests: int,
    candidate_programs: int = 1,
) -> ExperimentReport:
    outcomes: dict[str, int] = {}
    evidence: list[EvaluationEvidence] = []
    for result in results:
        outcomes[result.outcome] = outcomes.get(result.outcome, 0) + 1
        if result.evaluation_evidence is not None:
            evidence.append(
                EvaluationEvidence(
                    outcome=result.outcome,
                    normalized_progress=result.normalized_progress,
                    failure_type=result.failure_type,
                    failure_reason=result.failure_reason,
                    evidence=result.evaluation_evidence,
                    terminal_state=result.terminal_state,
                )
            )
    return ExperimentReport(
        experiment_id=experiment_id,
        execution_id=execution_id,
        candidate_programs=candidate_programs,
        episode_evaluations=sum(result.episode_evaluations for result in results),
        model_requests=model_requests,
        outcomes=outcomes,
        evaluation_evidence=evidence,
    )
