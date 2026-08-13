import pytest

from llm_gs.contracts import CandidateProgram, EpisodeResult, ResolvedSearchStrategyConfiguration
from llm_gs.search import (
    CEBS_SEARCH_STRATEGY_VERSION,
    CEBSSearchStrategy,
    CEMSearchStrategy,
    ScoredCandidate,
    resolve_search_strategy,
)


def test_cem_selects_the_best_development_candidate_and_records_elites() -> None:
    candidates = (
        ScoredCandidate(
            CandidateProgram(source="DEF run m( turnLeft m)"),
            (EpisodeResult(outcome="partial_completion", normalized_progress=0.2),),
        ),
        ScoredCandidate(
            CandidateProgram(source="DEF run m( move m)"),
            (EpisodeResult(outcome="success", normalized_progress=1.0),),
        ),
        ScoredCandidate(
            CandidateProgram(source="DEF run m( turnRight m)"),
            (EpisodeResult(outcome="partial_completion", normalized_progress=0.8),),
        ),
    )

    selected_index, provenance = CEMSearchStrategy(population_size=3, elite_count=2).select(
        candidates
    )

    assert selected_index == 1
    assert provenance["strategy"] == "cem"
    assert provenance["version"] == "v1"
    assert provenance["configured_population_size"] == 3
    assert provenance["configured_elite_count"] == 2
    assert provenance["observed_population_size"] == 3
    elite_progress = [
        entry["development_mean_normalized_progress"] for entry in provenance["elite_candidates"]
    ]
    assert elite_progress == [
        1.0,
        0.8,
    ]
    assert provenance["selection"] == provenance["elite_candidates"][0]


def test_search_strategy_registry_does_not_depend_on_task_or_orchestrator() -> None:
    strategy = resolve_search_strategy(
        ResolvedSearchStrategyConfiguration(
            name="cem", population_size=2, elite_count=1, seed=7
        )
    )

    assert strategy.name == "cem"
    assert strategy.version == "v1"


def test_cebs_selects_elites_and_records_versioned_selection_provenance() -> None:
    candidates = (
        ScoredCandidate(
            CandidateProgram(source="DEF run m( turnLeft m)"),
            (EpisodeResult(outcome="partial_completion", normalized_progress=0.2),),
        ),
        ScoredCandidate(
            CandidateProgram(source="DEF run m( move m)"),
            (EpisodeResult(outcome="success", normalized_progress=1.0),),
        ),
        ScoredCandidate(
            CandidateProgram(source="DEF run m( turnRight m)"),
            (EpisodeResult(outcome="partial_completion", normalized_progress=0.8),),
        ),
    )

    selected_index, provenance = CEBSSearchStrategy(population_size=3, elite_count=2).select(
        candidates
    )

    assert selected_index == 1
    assert provenance["strategy"] == "cebs"
    assert provenance["version"] == CEBS_SEARCH_STRATEGY_VERSION
    assert provenance["configured_population_size"] == 3
    assert provenance["configured_elite_count"] == 2
    assert provenance["observed_population_size"] == 3
    assert [
        entry["development_mean_normalized_progress"] for entry in provenance["elite_candidates"]
    ] == [1.0, 0.8]
    assert provenance["selection"] == provenance["elite_candidates"][0]


def test_cebs_resolves_through_the_versioned_search_strategy_contract() -> None:
    strategy = resolve_search_strategy(
        ResolvedSearchStrategyConfiguration(
            name="cebs", population_size=2, elite_count=1, seed=7
        )
    )

    assert strategy.name == "cebs"
    assert strategy.version == CEBS_SEARCH_STRATEGY_VERSION


def test_search_strategy_configuration_rejects_unknown_versions() -> None:
    with pytest.raises(ValueError, match="version"):
        ResolvedSearchStrategyConfiguration.model_validate(
            {"name": "cem", "population_size": 2, "elite_count": 1, "version": "v2"}
        )
