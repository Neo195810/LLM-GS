"""Versioned, task-agnostic Global Search contracts and implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from llm_gs.contracts import (
    CandidateProgram,
    EpisodeResult,
    ResolvedSearchStrategyConfiguration,
)
from llm_gs.reflection import _normalized_ast_hash

SEARCH_STRATEGY_VERSION = "v1"
CEBS_SEARCH_STRATEGY_VERSION = "v1"


@dataclass(frozen=True)
class ScoredCandidate:
    candidate: CandidateProgram
    results: tuple[EpisodeResult, ...]
    task_name: str | None = None


class SearchStrategy(Protocol):
    """Choose a Candidate Program from evaluated development candidates."""

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    def select(self, candidates: tuple[ScoredCandidate, ...]) -> tuple[int, dict[str, object]]: ...


def _selection_key(candidate: ScoredCandidate) -> tuple[float | int | str, ...]:
    outcomes = [result.outcome for result in candidate.results]
    progress = [result.normalized_progress for result in candidate.results]
    return (
        0 if all(outcome == "success" for outcome in outcomes) else 1,
        -sum(outcome == "success" for outcome in outcomes) / len(outcomes),
        -(sum(progress) / len(progress)),
        -min(progress),
        sum(result.episode_evaluations for result in candidate.results),
        _normalized_ast_hash(candidate.candidate.source, candidate.task_name),
    )


def _candidate_provenance(candidate: ScoredCandidate) -> dict[str, object]:
    results = candidate.results
    progress = [result.normalized_progress for result in results]
    return {
        "candidate_source_sha256": _normalized_ast_hash(
            candidate.candidate.source, candidate.task_name
        ),
        "development_success_rate": sum(result.outcome == "success" for result in results)
        / len(results),
        "development_mean_normalized_progress": sum(progress) / len(progress),
        "development_worst_normalized_progress": min(progress),
    }


def _select_elites(
    candidates: tuple[ScoredCandidate, ...],
    *,
    strategy: str,
    version: str,
    population_size: int,
    elite_count: int,
) -> tuple[int, dict[str, object]]:
    ranked = sorted(range(len(candidates)), key=lambda index: _selection_key(candidates[index]))
    elite_indices = ranked[: min(elite_count, len(ranked))]
    selected_index = elite_indices[0]
    return selected_index, {
        "strategy": strategy,
        "version": version,
        "configured_population_size": population_size,
        "configured_elite_count": elite_count,
        "observed_population_size": len(candidates),
        "elite_candidates": [_candidate_provenance(candidates[index]) for index in elite_indices],
        "selection": _candidate_provenance(candidates[selected_index]),
    }


@dataclass(frozen=True)
class SingleCandidateSearchStrategy:
    name: str = "single_candidate"
    version: str = SEARCH_STRATEGY_VERSION

    def select(self, candidates: tuple[ScoredCandidate, ...]) -> tuple[int, dict[str, object]]:
        selected_index = min(
            range(len(candidates)), key=lambda index: _selection_key(candidates[index])
        )
        return selected_index, {
            "strategy": self.name,
            "version": self.version,
            "selection": _candidate_provenance(candidates[selected_index]),
        }


@dataclass(frozen=True)
class CEMSearchStrategy:
    """Deterministically retain the highest-scoring elite candidate programs."""

    population_size: int
    elite_count: int
    name: str = "cem"
    version: str = SEARCH_STRATEGY_VERSION

    def select(self, candidates: tuple[ScoredCandidate, ...]) -> tuple[int, dict[str, object]]:
        return _select_elites(
            candidates,
            strategy=self.name,
            version=self.version,
            population_size=self.population_size,
            elite_count=self.elite_count,
        )


@dataclass(frozen=True)
class CEBSSearchStrategy:
    """Deterministically retain the highest-scoring CEBS elite candidate programs."""

    population_size: int
    elite_count: int
    name: str = "cebs"
    version: str = CEBS_SEARCH_STRATEGY_VERSION

    def select(self, candidates: tuple[ScoredCandidate, ...]) -> tuple[int, dict[str, object]]:
        return _select_elites(
            candidates,
            strategy=self.name,
            version=self.version,
            population_size=self.population_size,
            elite_count=self.elite_count,
        )


def resolve_search_strategy(configuration: ResolvedSearchStrategyConfiguration) -> SearchStrategy:
    name = configuration.name
    if name == "single_candidate":
        return SingleCandidateSearchStrategy()
    if name == "cem":
        return CEMSearchStrategy(
            population_size=configuration.population_size,
            elite_count=configuration.elite_count,
        )
    if name == "cebs":
        return CEBSSearchStrategy(
            population_size=configuration.population_size,
            elite_count=configuration.elite_count,
        )
    raise ValueError(f"unknown search strategy: {name}")
