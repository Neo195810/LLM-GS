# ruff: noqa: E501

from __future__ import annotations

from types import SimpleNamespace

import pytest

from llm_gs.manifest import task_prompt
from llm_gs.proposer import (
    MODEL_NAME,
    REASONING_EFFORT,
    CostBudget,
    ModelOutputFailure,
    OpenAIProposer,
)


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
