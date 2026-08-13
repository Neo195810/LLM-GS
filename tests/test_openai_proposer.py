# ruff: noqa: E501

from __future__ import annotations

from types import SimpleNamespace

import pytest

from llm_gs.proposer import MODEL_NAME, REASONING_EFFORT, ModelOutputFailure, OpenAIProposer


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
    assert "Validation error" in str(responses.calls[1]["input"])


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


def test_openai_proposer_blocks_input_before_sending_a_request() -> None:
    responses = FakeResponses(['{"source":"DEF run m( turnLeft m)"}'])

    with pytest.raises(ModelOutputFailure, match="input exceeds"):
        OpenAIProposer(responses, input_token_limit=1).propose("this prompt is too large")
    assert responses.calls == []
