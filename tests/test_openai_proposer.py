# ruff: noqa: E501

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from llm_gs.cli import _execute_with_failure_recording
from llm_gs.contracts import CandidateProgram, EpisodeResult, ExperimentSpecification
from llm_gs.execution import execute_resumable
from llm_gs.manifest import experiment_id, resolve_manifest, task_prompt
from llm_gs.proposer import (
    INVALID_OUTPUT_CONTENT_LIMIT,
    MODEL_NAME,
    REASONING_EFFORT,
    CostBudget,
    ModelOutputFailure,
    OpenAIProposer,
)
from llm_gs.storage import WorkspaceStore


class FakeResponses:
    def __init__(self, outputs: list[str], input_tokens: int = 10, output_tokens: int = 5) -> None:
        self._outputs = outputs
        self.calls: list[dict[str, object]] = []
        self._usage = SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_tokens_details=SimpleNamespace(cached_tokens=2),
        )

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_text=self._outputs.pop(0), usage=self._usage, status="completed"
        )


def test_openai_proposer_uses_pinned_structured_responses_request() -> None:
    responses = FakeResponses(['{"source":"DEF run m( turnLeft m)"}'])

    proposer = OpenAIProposer(responses)

    assert proposer.propose("make a program").source == "DEF run m( turnLeft m)"
    assert responses.calls[0]["model"] == MODEL_NAME
    assert responses.calls[0]["reasoning"] == {"effort": REASONING_EFFORT}
    assert responses.calls[0]["text"] == {
        "format": {
            "type": "json_schema",
            "name": "candidate_program_v1",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["source"],
                "properties": {"source": {"type": "string", "minLength": 1}},
            },
        }
    }
    assert proposer.records[0].cached_tokens == 2


def test_openai_proposer_corrects_invalid_output_at_most_twice() -> None:
    responses = FakeResponses(
        ["not json", '{"source":"not dsl"}', '{"source":"DEF run m( turnLeft m)"}']
    )

    candidate = OpenAIProposer(responses).propose("make a program")

    assert candidate.model_requests == 3
    assert len(responses.calls) == 3
    correction = str(responses.calls[1]["input"])
    assert "Validation error" in correction
    assert "Candidate program" in correction
    assert "DEF run m(" in correction
    assert "Allowed actions:" in correction
    assert "previous_response_id" not in responses.calls[1]


def test_openai_proposer_observes_redacted_invalid_outputs_before_correction() -> None:
    responses = FakeResponses(
        [
            '{"source":"not dsl sk-response-secret"}',
            '{"source":"DEF run m( turnLeft m)"}',
        ]
    )
    observed = []
    proposer = OpenAIProposer(responses)
    proposer.set_invalid_output_observer(observed.append)

    candidate = proposer.propose("Solve CleanHouse with sk-prompt-secret")

    assert candidate.model_requests == 2
    assert len(observed) == 1
    artifact = observed[0]
    assert artifact.phase == "initial"
    assert artifact.attempt == 1
    assert artifact.validation_stage == "dsl"
    assert artifact.finish_reason == "completed"
    assert artifact.response_original_length > len(artifact.response)
    assert "sk-response-secret" not in artifact.response
    assert "sk-response-secret" not in artifact.validation_error
    assert artifact.correction_prompt is not None
    assert "sk-prompt-secret" not in artifact.correction_prompt


def test_openai_proposer_observes_every_terminal_invalid_output_with_empty_response() -> None:
    responses = FakeResponses(["", "", ""])
    observed = []
    proposer = OpenAIProposer(responses)
    proposer.set_invalid_output_observer(observed.append)

    with pytest.raises(ModelOutputFailure, match="schema or DSL"):
        proposer.propose("make a program")

    assert [(artifact.attempt, artifact.correction_prompt is None) for artifact in observed] == [
        (1, False),
        (2, False),
        (3, True),
    ]
    assert all(artifact.response == "" for artifact in observed)


def test_openai_proposer_caps_invalid_artifact_after_redaction() -> None:
    responses = FakeResponses(["sk-secret-value " + "x" * (INVALID_OUTPUT_CONTENT_LIMIT + 100), '{"source":"DEF run m( turnLeft m)"}'])
    observed = []
    proposer = OpenAIProposer(responses)
    proposer.set_invalid_output_observer(observed.append)

    proposer.propose("make a program")

    assert "sk-secret-value" not in observed[0].response
    assert len(observed[0].response.encode("utf-8")) <= INVALID_OUTPUT_CONTENT_LIMIT
    assert observed[0].response_truncated is True


def test_workspace_store_keeps_invalid_output_content_private_and_content_addressed(
    tmp_path: Path,
) -> None:
    responses = FakeResponses(["not json", '{"source":"DEF run m( turnLeft m)"}'])
    observed = []
    proposer = OpenAIProposer(responses)
    proposer.set_invalid_output_observer(observed.append)
    proposer.propose("make a program")
    store = WorkspaceStore(tmp_path)  # type: ignore[arg-type]

    store.save_invalid_output_artifact("exec_000001", observed[0])
    store.save_invalid_output_artifact("exec_000001", observed[0])

    with sqlite3.connect(tmp_path / "attempt-store.sqlite3") as connection:
        row = connection.execute(
            "SELECT response_hash, correction_prompt_hash FROM invalid_output_artifacts"
        ).fetchone()
    assert row is not None
    assert all(item is not None and str(item).startswith("sha256:") for item in row)
    assert "not json" not in (tmp_path / "attempt-store.sqlite3").read_text(errors="ignore")
    with sqlite3.connect(tmp_path / "attempt-store.sqlite3") as connection:
        count = connection.execute("SELECT COUNT(*) FROM invalid_output_artifacts").fetchone()
    assert count == (2,)


def test_resumable_execution_persists_initial_invalid_output_before_successful_correction(
    tmp_path: Path,
) -> None:
    manifest = resolve_manifest(
        ExperimentSpecification.model_validate(
            {
                "display_name": "invalid-output-observation",
                "task": {"name": "offline.echo"},
                "seeds": {"task": [1]},
            }
        )
    )
    store = WorkspaceStore(tmp_path)
    responses = FakeResponses(["not json", '{"source":"DEF run m( turnLeft m)"}'])

    class SuccessfulEvaluator:
        def evaluate(self, candidate: CandidateProgram, task_seed: int) -> EpisodeResult:
            _ = candidate, task_seed
            return EpisodeResult(outcome="success")

    report, status = execute_resumable(
        manifest,
        experiment_id(manifest),
        store,
        OpenAIProposer(responses),
        SuccessfulEvaluator(),
    )

    assert report is not None
    assert status == "completed"
    artifacts = store.inspect_execution(report.execution_id)["invalid_output_artifacts"]
    assert artifacts == [
        {
            "phase": "initial",
            "attempt": 1,
            "validation_stage": "schema",
            "validation_error": "proposal source must be a non-empty string",
            "finish_reason": "completed",
            "input_tokens": 10,
            "output_tokens": 5,
            "cached_tokens": 2,
            "response_hash": artifacts[0]["response_hash"],
            "response_original_length": 8,
            "response_truncated": 0,
            "correction_prompt_hash": artifacts[0]["correction_prompt_hash"],
            "correction_prompt_original_length": artifacts[0]["correction_prompt_original_length"],
            "correction_prompt_truncated": 0,
        }
    ]


def test_resumable_execution_persists_terminal_initial_invalid_outputs(tmp_path: Path) -> None:
    manifest = resolve_manifest(
        ExperimentSpecification.model_validate(
            {
                "display_name": "terminal-invalid-output-observation",
                "task": {"name": "offline.echo"},
                "seeds": {"task": [1]},
            }
        )
    )
    store = WorkspaceStore(tmp_path)

    class SuccessfulEvaluator:
        def evaluate(self, candidate: CandidateProgram, task_seed: int) -> EpisodeResult:
            _ = candidate, task_seed
            return EpisodeResult(outcome="success")

    with pytest.raises(ModelOutputFailure, match="schema or DSL"):
        execute_resumable(
            manifest,
            experiment_id(manifest),
            store,
            OpenAIProposer(FakeResponses(["", "", ""])),
            SuccessfulEvaluator(),
        )

    execution_id = store.active_execution_id(experiment_id(manifest))
    assert execution_id is not None
    artifacts = store.inspect_execution(execution_id)["invalid_output_artifacts"]
    assert [artifact["attempt"] for artifact in artifacts] == [1, 2, 3]
    assert artifacts[-1]["correction_prompt_hash"] is None


def test_invalid_output_persistence_failure_is_an_infrastructure_failure(tmp_path: Path) -> None:
    manifest = resolve_manifest(
        ExperimentSpecification.model_validate(
            {
                "display_name": "artifact-persistence-failure",
                "task": {"name": "offline.echo"},
                "seeds": {"task": [1]},
            }
        )
    )

    class FailingArtifactStore(WorkspaceStore):
        def save_invalid_output_artifact(self, execution_id: str, artifact: object) -> None:
            _ = execution_id, artifact
            raise sqlite3.OperationalError("artifact storage unavailable")

    store = FailingArtifactStore(tmp_path)
    with pytest.raises(ValueError, match="infrastructure failure"):
        _execute_with_failure_recording(
            manifest,
            experiment_id(manifest),
            store,
            argparse.Namespace(),
            model=OpenAIProposer(FakeResponses(["not json"])),
        )

    with sqlite3.connect(tmp_path / "attempt-store.sqlite3") as connection:
        kinds = connection.execute("SELECT kind FROM execution_failures").fetchall()
    assert kinds == [("infrastructure",)]


def test_correction_feedback_is_bounded_and_redacts_secrets() -> None:
    responses = FakeResponses(
        [
            '{"source":"not dsl"}',
            '{"source":"still not dsl"}',
            '{"source":"DEF run m( turnLeft m)"}',
        ]
    )

    OpenAIProposer(responses).propose(
        "Solve CleanHouse with token sk-test-secret-value and " + "x" * 20000
    )

    correction = str(responses.calls[1]["input"])
    assert len(correction) <= 8000
    assert "sk-test-secret-value" not in correction
    assert "Candidate program: not dsl" in correction


def test_repair_feedback_includes_bounded_evaluation_evidence() -> None:
    responses = FakeResponses(['{"source":"DEF run m( move m)"}'])

    OpenAIProposer(responses).repair(
        "Repair CleanHouse using evidence " + "x" * 20000 + " sk-secret-value"
    )

    repair_prompt = str(responses.calls[0]["input"])
    assert len(repair_prompt) <= 8000
    assert "Allowed actions: move" in repair_prompt
    assert "sk-secret-value" not in repair_prompt


def test_openai_proposer_blocks_token_budget_overrun() -> None:
    responses = FakeResponses(
        ['{"source":"DEF run m( turnLeft m)"}'], input_tokens=9, output_tokens=2
    )

    with pytest.raises(ModelOutputFailure, match="token budget"):
        OpenAIProposer(responses, input_token_limit=8, output_token_limit=2).propose(
            "make a program"
        )


def test_openai_proposer_retries_an_invalid_karel_dsl() -> None:
    responses = FakeResponses(
        ['{"source":"DEF run invalid"}', '{"source":"DEF run m( turnLeft m)"}']
    )

    assert OpenAIProposer(responses).propose("make a program").model_requests == 2


def test_openai_proposer_retries_an_invalid_task_specific_dsl() -> None:
    responses = FakeResponses(
        ['{"source":"CLEANHOUSE"}', '{"source":"DEF run m( turnLeft m)"}']
    )

    assert OpenAIProposer(responses).propose("Solve CleanHouse").model_requests == 2


def test_openai_proposer_safely_extracts_and_normalizes_code_fenced_source() -> None:
    responses = FakeResponses(["```\n DEF   run m(   turnLeft   m) \n```"])

    candidate = OpenAIProposer(responses).propose("make a program")

    assert candidate.source == "DEF run m( turnLeft m)"


def test_openai_proposer_repair_includes_task_dsl_contract() -> None:
    responses = FakeResponses(['{"source":"DEF run m( move m)"}'])

    candidate = OpenAIProposer(responses).repair("Repair CleanHouse using evidence")

    assert candidate.source == "DEF run m( move m)"
    assert "Allowed actions: move" in str(responses.calls[0]["input"])


def test_openai_proposer_blocks_input_before_sending_a_request() -> None:
    responses = FakeResponses(['{"source":"DEF run m( turnLeft m)"}'])

    with pytest.raises(ModelOutputFailure, match="input exceeds"):
        OpenAIProposer(responses, input_token_limit=1).propose("this prompt is too large")
    assert responses.calls == []


def test_openai_proposer_enforces_shared_total_cost_cap() -> None:
    budget = CostBudget(0.01)
    responses = FakeResponses(['{"source":"DEF run m( turnLeft m)"}'])

    with pytest.raises(ModelOutputFailure, match="total cost cap"):
        OpenAIProposer(responses, total_cost_budget=budget).propose("make a program")
    assert responses.calls == []


@pytest.mark.parametrize("task_name", ["CleanHouse", "FourCorners", "DoorKey", "RedBlueDoor"])
def test_task_prompt_includes_exact_dsl_envelope_and_example(task_name: str) -> None:
    prompt = task_prompt(task_name)

    assert "DEF run m(" in prompt
    assert "Example valid source" in prompt
