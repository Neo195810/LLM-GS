from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TaskSpecification(StrictContract):
    name: Literal["CleanHouse", "FourCorners", "offline.echo"]


class SeedSpecification(StrictContract):
    task: list[int] = Field(min_length=1)
    search: int = 0
    replicate: int = Field(default=0, ge=0)


class SeedSuiteSpecification(StrictContract):
    version: Literal[1] = 1
    memory_training: list[int] = Field(min_length=1)
    development: list[int] = Field(min_length=1)
    held_out: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def partitions_are_disjoint(self) -> SeedSuiteSpecification:
        partitions = (self.memory_training, self.development, self.held_out)
        if sum(len(partition) for partition in partitions) != len(
            set().union(*[set(partition) for partition in partitions])
        ):
            raise ValueError("seed suite partitions must be disjoint")
        return self


class FailureStrategySpecification(StrictContract):
    name: Literal["regenerate", "reflect", "memory_repair", "memory_reflect"] = "regenerate"
    max_repair_cycles: int = Field(default=3, ge=0, le=3)


class SearchStrategySpecification(StrictContract):
    name: Literal["single_candidate", "cem"] = "single_candidate"
    population_size: int = Field(default=1, ge=1)
    elite_count: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def has_valid_elite_count(self) -> SearchStrategySpecification:
        if self.elite_count > self.population_size:
            raise ValueError("elite_count must not exceed population_size")
        if self.name == "single_candidate" and (self.population_size, self.elite_count) != (1, 1):
            raise ValueError("single_candidate requires population_size and elite_count of one")
        return self


class ResolvedSearchStrategyConfiguration(SearchStrategySpecification):
    version: Literal["v1"] = "v1"
    seed: int = 0
    replicate: int = Field(default=0, ge=0)


class ExperimentSpecification(StrictContract):
    spec_version: Literal[1] = 1
    display_name: str = Field(min_length=1)
    task: TaskSpecification
    seeds: SeedSpecification | None = None
    seed_suite: SeedSuiteSpecification | None = None
    memory_snapshot_id: str | None = None
    search_strategy: SearchStrategySpecification = Field(
        default_factory=SearchStrategySpecification
    )
    failure_strategy: FailureStrategySpecification = Field(
        default_factory=FailureStrategySpecification
    )

    @model_validator(mode="after")
    def has_exactly_one_seed_definition(self) -> ExperimentSpecification:
        if (self.seeds is None) == (self.seed_suite is None):
            raise ValueError("provide exactly one of seeds or seed_suite")
        return self


class ExperimentManifest(StrictContract):
    manifest_version: Literal[1] = 1
    code: dict[str, str]
    dependencies: dict[str, str]
    components: dict[str, str]
    contracts: dict[str, str]
    runtime: dict[str, str]
    model: dict[str, str | int]
    task: dict[str, str | int]
    search_strategy: dict[str, str | int]
    failure_strategy: dict[str, str | int]
    budgets: dict[str, int]
    memory_snapshot: dict[str, str | bool]
    specification: dict[str, object]


class CandidateProgram(StrictContract):
    source: str
    model_requests: int = 1


class EpisodeResult(StrictContract):
    outcome: Literal[
        "success", "partial_completion", "policy_crash", "invalid_program", "evaluation_error"
    ]
    episode_evaluations: int = 1
    normalized_progress: float = 1.0
    failure_type: str | None = None
    failure_reason: str | None = None
    evaluation_evidence: dict[str, object] | None = None
    terminal_state: str | None = None


class EvaluationEvidence(StrictContract):
    outcome: Literal[
        "success", "partial_completion", "policy_crash", "invalid_program", "evaluation_error"
    ]
    normalized_progress: float
    failure_type: str | None = None
    failure_reason: str | None = None
    evidence: dict[str, object] | None = None
    terminal_state: str | None = None


class Diagnosis(StrictContract):
    version: Literal[1] = 1
    evidence_index: int = Field(ge=0)
    observation: str = Field(min_length=1)
    hypothesis: str = Field(min_length=1)


class RepairIntent(StrictContract):
    version: Literal[1] = 1
    intended_change: str = Field(min_length=1)
    preserved_behavior: str = Field(min_length=1)


class RepairAttempt(StrictContract):
    parent_source: str
    candidate: CandidateProgram
    diagnosis: Diagnosis
    intent: RepairIntent
    normalized_ast_difference: str
    round: int = Field(ge=1)


class MemoryEntry(StrictContract):
    version: Literal[1] = 1
    entry_id: str
    task: Literal["CleanHouse", "FourCorners"]
    failure_type: str
    failure_reason: str
    normalized_ast_hash: str
    state_features: dict[str, int]
    evidence: dict[str, int | str]
    source_attempt_id: str


class RetrievalCandidateComponents(StrictContract):
    task_compatible: bool
    failure_type_match: bool
    failure_reason_match: bool
    state_distance: int = Field(ge=0)
    ast_feature: str
    evidence_quality: int = Field(ge=0)
    improvement: int
    novelty: int = Field(ge=0)


class RetrievalOutcome(StrictContract):
    version: Literal[2] = 2
    query_failure_type: str
    query_failure_reason: str
    selected_entry_ids: list[str]
    reason_codes: dict[str, list[str]]
    candidate_components: dict[str, RetrievalCandidateComponents]
    subsequent_improvement: bool | None = None
    subsequent_failure_type_changed: bool | None = None
    subsequent_success: bool | None = None
    subsequent_attempted: bool | None = None


class ExperimentReport(StrictContract):
    report_version: Literal[1] = 1
    experiment_id: str
    execution_id: str
    status: Literal["completed"] = "completed"
    candidate_programs: int
    episode_evaluations: int
    model_requests: int
    outcomes: dict[str, int]
    evaluation_evidence: list[EvaluationEvidence] = Field(default_factory=list)
    audit: dict[str, object] = Field(default_factory=dict)
