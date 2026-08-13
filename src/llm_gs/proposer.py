from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol, cast

from openai import OpenAI

from llm_gs.contracts import CandidateProgram
from prog_policies.karel.dsl import KarelDSL

MODEL_NAME = "gpt-5.6-luna"
REASONING_EFFORT = "medium"
PROPOSAL_SCHEMA_VERSION = 1
PROPOSAL_SCHEMA = {
    "name": "candidate_program_v1",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["source"],
        "properties": {"source": {"type": "string", "minLength": 1}},
    },
}


class ResponsesClient(Protocol):
    def create(self, **kwargs: object) -> object: ...


class ModelOutputFailure(ValueError):
    """The model exhausted its bounded output-format corrections."""


@dataclass(frozen=True)
class ModelRequestRecord:
    attempt: int
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    finish_reason: str | None
    warning: str | None


class OpenAIProposer:
    """Bounded, schema-constrained Responses API adapter with no secret persistence."""

    def __init__(
        self,
        client: ResponsesClient | None = None,
        input_token_limit: int = 4096,
        output_token_limit: int = 1024,
        max_cost_usd: float = 1.0,
    ) -> None:
        self._client: ResponsesClient = (
            client if client is not None else cast(ResponsesClient, OpenAI().responses)
        )
        self._input_token_limit = input_token_limit
        self._output_token_limit = output_token_limit
        self._max_cost_usd = max_cost_usd
        self.records: list[ModelRequestRecord] = []

    def propose(self, prompt: str) -> CandidateProgram:
        request_prompt = prompt
        if _token_estimate(request_prompt) > self._input_token_limit:
            raise ModelOutputFailure("request input exceeds the configured token budget")
        for attempt in range(1, 4):
            response = self._client.create(
                model=MODEL_NAME,
                reasoning={"effort": REASONING_EFFORT},
                input=request_prompt,
                max_output_tokens=self._output_token_limit,
                text={"format": {"type": "json_schema", **PROPOSAL_SCHEMA}},
            )
            self._record_usage(response, attempt)
            try:
                source = _proposal_source(response)
                _validate_dsl(source)
                return CandidateProgram(source=source, model_requests=attempt)
            except (AssertionError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                if attempt == 3:
                    raise ModelOutputFailure(
                        "model output failed schema or DSL validation"
                    ) from error
                request_prompt = _correction_prompt(prompt, str(error))
        raise AssertionError("unreachable")

    def _record_usage(self, response: object, attempt: int) -> None:
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0))
        output_tokens = int(getattr(usage, "output_tokens", 0))
        details = getattr(usage, "input_tokens_details", None)
        cached_tokens = int(getattr(details, "cached_tokens", 0))
        if input_tokens > self._input_token_limit or output_tokens > self._output_token_limit:
            raise ModelOutputFailure("model request exceeds the configured token budget")
        used_tokens = input_tokens + output_tokens
        if _estimated_cost_usd(input_tokens, output_tokens) > self._max_cost_usd:
            raise ModelOutputFailure("model request exceeds the configured cost cap")
        total_limit = self._input_token_limit + self._output_token_limit
        warning = "token_budget_80_percent" if used_tokens * 100 >= total_limit * 80 else None
        self.records.append(
            ModelRequestRecord(
                attempt=attempt,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_tokens=cached_tokens,
                finish_reason=getattr(response, "status", None),
                warning=warning,
            )
        )


def _proposal_source(response: object) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text is None:
        raise ValueError("response contains no output text")
    payload = json.loads(str(output_text))
    source = payload["source"]
    if not isinstance(source, str) or not source:
        raise ValueError("proposal source must be a non-empty string")
    return source


def _validate_dsl(source: str) -> None:
    KarelDSL().parse_str_to_node(source)  # type: ignore[no-untyped-call]


def _token_estimate(prompt: str) -> int:
    return (len(prompt.encode("utf-8")) + 3) // 4


def _estimated_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Conservative per-request ceiling used only to enforce an explicit client cap."""
    return input_tokens * 0.000_005 + output_tokens * 0.000_015


def _correction_prompt(original_prompt: str, validation_error: str) -> str:
    return (
        f"{original_prompt}\nReturn only the proposal schema JSON. "
        f"Validation error: {validation_error}"
    )
