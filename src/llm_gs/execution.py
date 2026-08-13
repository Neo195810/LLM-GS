from __future__ import annotations

from typing import Protocol, TypedDict, runtime_checkable

from llm_gs.contracts import (
    CandidateProgram,
    Diagnosis,
    EpisodeResult,
    EvaluationEvidence,
    ExperimentManifest,
    ExperimentReport,
    MemoryEntry,
    RepairIntent,
)
from llm_gs.manifest import CLEAN_HOUSE_PROMPT, FINAL_CANDIDATE_SELECTION_RULE, OFFLINE_PROMPT
from llm_gs.memory import StructuredRetriever, curate_clean_house_attempt, serialize_repair_context
from llm_gs.reflection import RepairCycle, RepeatedRepairError, _normalized_ast_hash
from llm_gs.storage import WorkspaceStore
from llm_gs.v1_adapter import V1Adapter, V1ExecutionLimits


class ModelClient(Protocol):
    def propose(self, prompt: str) -> CandidateProgram: ...


class Evaluator(Protocol):
    def evaluate(self, candidate: CandidateProgram, task_seed: int) -> EpisodeResult: ...


class ResolvedSeedSuite(TypedDict):
    version: int
    memory_training: list[int]
    development: list[int]
    held_out: list[int]


@runtime_checkable
class Repairer(Protocol):
    def repair(self, prompt: str) -> CandidateProgram: ...


class FakeOpenAIClient:
    def propose(self, prompt: str) -> CandidateProgram:
        if prompt.startswith(("Repair CleanHouse", "Reflect on evidence then repair CleanHouse")):
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
    prompt: str | None = None,
    repair_round: int = 1,
    seen_ast_hashes: set[str] | None = None,
    reflect: bool = True,
    retrieved_data: str | None = None,
) -> CandidateProgram:
    diagnosis = (
        cycle.diagnose(result, evidence_index=0, retrieved_data=retrieved_data)
        if reflect
        else Diagnosis(
            evidence_index=0,
            observation="Retrieved memory provides a prior repair pattern.",
            hypothesis="Apply the retrieved repair pattern while preserving valid Karel DSL.",
        )
    )
    intent = RepairIntent(
        intended_change="replace the stalled action sequence",
        preserved_behavior="a complete valid Karel DSL program",
    )
    candidate = repairer.repair(prompt or f"Repair CleanHouse using: {diagnosis.observation}")
    repair = cycle.repair(parent, diagnosis, intent, candidate, repair_round, seen_ast_hashes)
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
            repair_source,
            repair_round=1,
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
    if isinstance(manifest.specification.get("seed_suite"), dict):
        return _execute_frozen_memory_protocol(manifest, experiment_id, store, model, evaluator)
    if manifest.failure_strategy["name"] in {"reflect", "memory_repair", "memory_reflect"}:
        return _execute_reflect(manifest, experiment_id, store, model, evaluator, stop_after)
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
        experiment_id,
        active_execution_id,
        results,
        store.model_requests(active_execution_id),
        audit=store.execution_audit(active_execution_id),
    )
    store.save(manifest, report)
    return report, "completed"


def _execute_frozen_memory_protocol(
    manifest: ExperimentManifest,
    experiment_id: str,
    store: WorkspaceStore,
    model: ModelClient,
    evaluator: Evaluator,
) -> tuple[ExperimentReport, str]:
    """Build Frozen Memory, select on development seeds, then evaluate held-out once."""
    if not isinstance(model, Repairer) and manifest.failure_strategy["name"] != "regenerate":
        raise ValueError("frozen memory protocol requires a repair-capable model")
    suite = _seed_suite(manifest)
    execution_id = store.active_execution_id(experiment_id)
    if execution_id is not None:
        raise ValueError("resuming the frozen memory protocol is not yet supported")

    store.preregister_paired_protocol(manifest)
    store.preregister_frozen_manifest(manifest, experiment_id)
    if store.has_completed_execution(experiment_id):
        return store.latest_report(experiment_id), "completed"

    execution_id = store.next_execution_id(experiment_id)
    initial_candidate = model.propose(CLEAN_HOUSE_PROMPT)
    store.begin_execution_for_experiment(
        manifest,
        experiment_id,
        execution_id,
        initial_candidate.source,
        initial_candidate.model_requests,
    )
    training_results = _evaluate_candidate(
        store, execution_id, initial_candidate, suite["memory_training"], evaluator
    )
    training_entries = [
        curate_clean_house_attempt(
            f"{execution_id}:memory-training:{index}", initial_candidate.source, result
        )
        for index, result in enumerate(training_results)
        if result.outcome != "success"
    ]
    training_entries = _balanced_memory_entries(training_entries)
    for entry in training_entries:
        store.save_memory_entry(entry)
    snapshot_entries = store.freeze_memory_snapshot(execution_id, training_entries)

    candidates: list[tuple[CandidateProgram, list[EpisodeResult]]] = []
    current_candidate = initial_candidate
    current_results = _evaluate_candidate(
        store, execution_id, current_candidate, suite["development"], evaluator
    )
    candidates.append((current_candidate, current_results))
    strategy = str(manifest.failure_strategy["name"])
    if strategy != "regenerate" and not isinstance(model, Repairer):
        raise AssertionError(
            "non-regenerate frozen memory protocols require a repair-capable model"
        )
    cycle = RepairCycle(int(manifest.failure_strategy["max_repair_cycles"]))
    seen_ast_hashes = {_normalized_ast_hash(current_candidate.source)}
    for repair_round in range(1, int(manifest.failure_strategy["max_repair_cycles"]) + 1):
        failed_results = [result for result in current_results if result.outcome != "success"]
        if not failed_results:
            break
        failed_result = failed_results[0]
        if strategy == "regenerate":
            replacement = model.propose(CLEAN_HOUSE_PROMPT)
            if store.model_requests(execution_id) + replacement.model_requests > int(
                manifest.budgets["model_requests"]
            ):
                break
            store.add_model_requests(execution_id, replacement.model_requests)
            current_candidate = replacement
            current_results = _evaluate_candidate(
                store, execution_id, current_candidate, suite["development"], evaluator
            )
            candidates.append((current_candidate, current_results))
            seen_ast_hashes.add(_normalized_ast_hash(current_candidate.source))
            continue
        if not isinstance(model, Repairer):
            raise AssertionError("non-regenerate strategy requires a repair-capable model")
        memory_context: str | None = None
        retrieval_id: int | None = None
        if strategy in {"memory_repair", "memory_reflect"}:
            retrieved, retrieval = StructuredRetriever(tuple(snapshot_entries)).retrieve(
                failed_result
            )
            retrieval_id = store.save_retrieval_outcome(execution_id, retrieval)
            memory_context = serialize_repair_context(failed_result, retrieved)
        else:
            memory_context = serialize_repair_context(failed_result, [])
        prompt_prefix = (
            "Reflect on evidence then repair" if strategy == "memory_reflect" else "Repair"
        )
        try:
            repaired_candidate = reflect_once(
                current_candidate,
                failed_result,
                model,
                cycle,
                execution_id,
                store,
                f"{prompt_prefix} CleanHouse using data: "
                f"{memory_context}",
                repair_round=repair_round,
                seen_ast_hashes=seen_ast_hashes,
                reflect=strategy != "memory_repair",
                retrieved_data=memory_context,
            )
        except RepeatedRepairError:
            if retrieval_id is not None:
                store.record_no_retrieval_impact(retrieval_id)
            break
        if store.model_requests(execution_id) + repaired_candidate.model_requests > int(
            manifest.budgets["model_requests"]
        ):
            if retrieval_id is not None:
                store.record_no_retrieval_impact(retrieval_id)
            break
        store.add_model_requests(execution_id, repaired_candidate.model_requests)
        current_candidate = repaired_candidate
        current_results = _evaluate_candidate(
            store, execution_id, current_candidate, suite["development"], evaluator
        )
        if retrieval_id is not None:
            store.record_retrieval_impact(retrieval_id, failed_results, current_results)
        candidates.append((current_candidate, current_results))
        seen_ast_hashes.add(_normalized_ast_hash(current_candidate.source))

    selected_candidate, selection = _select_final_candidate(candidates)
    held_out_results = _evaluate_candidate(
        store, execution_id, selected_candidate, suite["held_out"], evaluator
    )
    audit = store.execution_audit(execution_id)
    audit["memory_protocol"] = str(manifest.memory_snapshot.get("protocol", "none"))
    total_episode_evaluations = (
        sum(len(results) for _, results in candidates)
        + len(training_results)
        + len(held_out_results)
    )
    audit["frozen_memory_protocol"] = {
        "memory_snapshot_id": store.memory_snapshot_id(execution_id),
        "primary_metric": {
            "name": "held_out_success_rate",
            "value": _success_rate(held_out_results),
        },
        "secondary_metrics": {
            "development_candidate_count": len(candidates),
            "episode_evaluations": total_episode_evaluations,
            "model_requests": store.model_requests(execution_id),
            "repair_attempts": len(candidates) - 1,
        },
        "seed_suite": suite,
        "selection": {
            **selection,
            "held_out_evaluations": len(held_out_results),
            "rule": FINAL_CANDIDATE_SELECTION_RULE,
            "selected_before_held_out": True,
        },
    }
    report = _report_from_results(
        experiment_id,
        execution_id,
        held_out_results,
        store.model_requests(execution_id),
        candidate_programs=len(candidates),
        audit=audit,
    ).model_copy(update={"episode_evaluations": total_episode_evaluations})
    store.save(manifest, report)
    return report, "completed"


def _evaluate_candidate(
    store: WorkspaceStore,
    execution_id: str,
    candidate: CandidateProgram,
    seeds: list[int],
    evaluator: Evaluator,
) -> list[EpisodeResult]:
    results = [evaluator.evaluate(candidate, seed) for seed in seeds]
    for seed, result in zip(seeds, results, strict=True):
        store.record_evaluation(execution_id, seed, candidate.source, result.model_dump_json())
    return results


def _seed_suite(manifest: ExperimentManifest) -> ResolvedSeedSuite:
    seed_suite = manifest.specification.get("seed_suite")
    if not isinstance(seed_suite, dict):
        raise ValueError("resolved manifest contains invalid seed suite")
    if any(
        not isinstance(seed_suite.get(partition), list)
        for partition in ("memory_training", "development", "held_out")
    ):
        raise ValueError("resolved manifest contains invalid seed suite")
    return {
        "version": int(seed_suite["version"]),
        "memory_training": [int(seed) for seed in seed_suite["memory_training"]],
        "development": [int(seed) for seed in seed_suite["development"]],
        "held_out": [int(seed) for seed in seed_suite["held_out"]],
    }


def _select_final_candidate(
    candidates: list[tuple[CandidateProgram, list[EpisodeResult]]],
) -> tuple[CandidateProgram, dict[str, object]]:
    if not candidates:
        raise ValueError("cannot select a final candidate without development results")

    def key(item: tuple[CandidateProgram, list[EpisodeResult]]) -> tuple[float | int | str, ...]:
        candidate, results = item
        outcomes = [result.outcome for result in results]
        outcome_rank = 0 if all(outcome == "success" for outcome in outcomes) else 1
        progress = [result.normalized_progress for result in results]
        return (
            outcome_rank,
            -_success_rate(results),
            -(sum(progress) / len(progress)),
            -min(progress),
            sum(result.episode_evaluations for result in results),
            _normalized_ast_hash(candidate.source),
        )

    selected, results = min(candidates, key=key)
    return selected, {
        "candidate_source_sha256": _normalized_ast_hash(selected.source),
        "development_success_rate": _success_rate(results),
        "development_mean_normalized_progress": sum(
            result.normalized_progress for result in results
        )
        / len(results),
        "development_worst_normalized_progress": min(
            result.normalized_progress for result in results
        ),
    }


def _success_rate(results: list[EpisodeResult]) -> float:
    return sum(result.outcome == "success" for result in results) / len(results)


def _balanced_memory_entries(entries: list[MemoryEntry]) -> list[MemoryEntry]:
    """Keep one stable representative per shared failure category for Frozen Memory."""
    representatives: dict[tuple[str, str], MemoryEntry] = {}
    for entry in entries:
        key = (entry.failure_type, entry.failure_reason)
        representatives.setdefault(key, entry)
    return list(representatives.values())


def _execute_reflect(
    manifest: ExperimentManifest,
    experiment_id: str,
    store: WorkspaceStore,
    model: ModelClient,
    evaluator: Evaluator,
    stop_after: int | None = None,
) -> tuple[ExperimentReport | None, str]:
    if not isinstance(model, Repairer):
        raise ValueError("reflect strategy requires a repair-capable model")
    execution_id = store.active_execution_id(experiment_id)
    if execution_id is None:
        execution_id = store.next_execution_id(experiment_id)
        candidate = model.propose(CLEAN_HOUSE_PROMPT)
        store.begin_execution_for_experiment(
            manifest, experiment_id, execution_id, candidate.source, candidate.model_requests
        )
    else:
        candidate = CandidateProgram(source=store.execution_candidate_source(execution_id))
    seeds = _task_seeds(manifest)
    strategy = str(manifest.failure_strategy["name"])
    is_online_memory = strategy in {"memory_repair", "memory_reflect"}
    if is_online_memory:
        store.fork_memory_lineage(
            execution_id,
            [],
            {
                "method": strategy,
                "replicate": int(manifest.search_strategy["replicate"]),
                "search_strategy": str(manifest.search_strategy["name"]),
            },
            parent_snapshot_id=(
                str(manifest.memory_snapshot["id"])
                if manifest.memory_snapshot["id"] != "fork-on-run"
                else None
            ),
        )
    completed_rows = store.completed_episode_results(execution_id)
    initial_results = [EpisodeResult.model_validate_json(row) for row in completed_rows]
    completed = 0
    work = store.next_pending_work(experiment_id)
    while work is not None:
        initial_result = evaluator.evaluate(candidate, work.seed)
        store.complete_work(work, initial_result.model_dump_json())
        initial_results.append(initial_result)
        completed += 1
        if stop_after is not None and completed >= stop_after:
            return None, "interrupted"
        work = store.next_pending_work(experiment_id)
    final_candidate = candidate
    final_results = initial_results
    all_results = list(initial_results)
    cycle = RepairCycle(int(manifest.failure_strategy["max_repair_cycles"]))
    maximum_candidates = min(
        1 + int(manifest.failure_strategy["max_repair_cycles"]),
        int(manifest.budgets["episode_evaluations"]) // len(seeds),
    )
    model_request_budget = int(manifest.budgets["model_requests"])
    model_requests_used = candidate.model_requests
    seen_ast_hashes = {_normalized_ast_hash(candidate.source)}
    for repair_round in range(1, maximum_candidates):
        failed_results = [result for result in final_results if result.outcome != "success"]
        if not failed_results:
            break
        initial_result = failed_results[0]
        if is_online_memory:
            updates = [
                curate_clean_house_attempt(
                    f"{execution_id}:repair:{repair_round - 1}:{index}",
                    final_candidate.source,
                    result,
                )
                for index, result in enumerate(failed_results)
            ]
            # The full seed set has completed, so this is a stable sequential
            # decision boundary before retrieval and repair.
            store.append_memory_lineage_entries(execution_id, updates)
            retrieved, retrieval = StructuredRetriever(
                tuple(store.memory_lineage_entries(execution_id))
            ).retrieve(
                initial_result
            )
            retrieval_id = store.save_retrieval_outcome(execution_id, retrieval)
            memory_context = serialize_repair_context(initial_result, retrieved)
            prefix = "Reflect on evidence then repair" if strategy == "memory_reflect" else "Repair"
            repair_prompt = f"{prefix} CleanHouse using memory: {memory_context}"
        else:
            repair_prompt = None
            memory_context = None
        try:
            repaired_candidate = reflect_once(
                final_candidate,
                initial_result,
                model,
                cycle,
                execution_id,
                store,
                repair_prompt,
                repair_round=repair_round,
                seen_ast_hashes=seen_ast_hashes,
                reflect=strategy != "memory_repair",
                retrieved_data=memory_context,
            )
        except RepeatedRepairError:
            if is_online_memory:
                store.record_no_retrieval_impact(retrieval_id)
            break
        if model_requests_used + repaired_candidate.model_requests > model_request_budget:
            if is_online_memory:
                store.record_no_retrieval_impact(retrieval_id)
            break
        model_requests_used += repaired_candidate.model_requests
        store.add_model_requests(execution_id, repaired_candidate.model_requests)
        repaired_results = [evaluator.evaluate(repaired_candidate, seed) for seed in seeds]
        for seed, result in zip(seeds, repaired_results, strict=True):
            store.record_evaluation(
                execution_id, seed, repaired_candidate.source, result.model_dump_json()
            )
        if is_online_memory:
            store.record_retrieval_impact(retrieval_id, final_results, repaired_results)
        made_improvement = _has_repair_improvement(final_results, repaired_results)
        seen_ast_hashes.add(_normalized_ast_hash(repaired_candidate.source))
        final_candidate = repaired_candidate
        final_results = repaired_results
        all_results.extend(repaired_results)
        if not made_improvement:
            break
    audit = store.execution_audit(execution_id)
    audit["memory_protocol"] = str(manifest.memory_snapshot.get("protocol", "none"))
    if is_online_memory:
        audit["memory_lineage"] = store.memory_lineage_audit(execution_id)
    report = _report_from_results(
        experiment_id,
        execution_id,
        all_results,
        store.model_requests(execution_id),
        candidate_programs=len(all_results) // len(seeds),
        audit=audit,
    )
    store.save(manifest, report)
    return report, "completed"


def _has_repair_improvement(
    previous: list[EpisodeResult], repaired: list[EpisodeResult]
) -> bool:
    if any(result.outcome == "success" for result in repaired):
        return True
    return sum(result.normalized_progress for result in repaired) > sum(
        result.normalized_progress for result in previous
    )


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
    audit: dict[str, object] | None = None,
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
        audit=audit or {},
    )
