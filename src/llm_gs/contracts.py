from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TaskSpecification(StrictContract):
    name: Literal["CleanHouse", "offline.echo"]


class SeedSpecification(StrictContract):
    task: list[int] = Field(min_length=1)
    search: int = 0


class ExperimentSpecification(StrictContract):
    spec_version: Literal[1] = 1
    display_name: str = Field(min_length=1)
    task: TaskSpecification
    seeds: SeedSpecification


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


class ExperimentReport(StrictContract):
    report_version: Literal[1] = 1
    experiment_id: str
    execution_id: str
    status: Literal["completed"] = "completed"
    candidate_programs: int
    episode_evaluations: int
    model_requests: int
    outcomes: dict[str, int]
