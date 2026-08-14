from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, cast

from openai import OpenAI

from llm_gs.contracts import CandidateProgram
from prog_policies.karel.dsl import KarelDSL
from prog_policies.minigrid.dsl import MinigridDSL

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
CORRECTION_ATTEMPTS = 2
FEEDBACK_LIMIT = 8000
INVALID_OUTPUT_CONTENT_LIMIT = 64 * 1024
GENERIC_DSL_CONTRACT = (
    "Task name is unspecified. Return JSON with only source. Use exact DSL syntax "
    "DEF run m( <statements> m), and use only actions valid for the identified "
    "task. Allowed actions: move, turnLeft, turnRight, pickMarker, putMarker, "
    "left, right, forward, pickup, drop, toggle. Never output pseudocode, "
    "Markdown, or Python."
)
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(sk-)[A-Za-z0-9_-]+"),
    re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~-]+"),
    re.compile(r"(?i)(api[_ -]?key\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"(?i)(token\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"(?i)(password\s*[:=]\s*)[^\s,;]+"),
)


class ResponsesClient(Protocol):
    def create(self, **kwargs: object) -> object: ...


class ModelOutputFailure(ValueError):
    """The model exhausted its bounded output-format corrections."""


class ProposalValidationError(ValueError):
    """A candidate failed schema extraction or task DSL validation."""

    def __init__(self, stage: str, detail: str) -> None:
        self.stage = stage
        super().__init__(detail)


class CostBudget:
    """Shared, conservative dollar budget for one or more proposer instances."""

    def __init__(self, max_cost_usd: float) -> None:
        self.max_cost_usd = max_cost_usd
        self.used_cost_usd = 0.0

    def reserve(self, maximum_cost_usd: float) -> float:
        if self.used_cost_usd + maximum_cost_usd > self.max_cost_usd:
            raise ModelOutputFailure("model request exceeds the configured total cost cap")
        self.used_cost_usd += maximum_cost_usd
        return maximum_cost_usd

    def settle(self, reserved_cost_usd: float, actual_cost_usd: float) -> None:
        self.used_cost_usd -= reserved_cost_usd - actual_cost_usd


@dataclass(frozen=True)
class ModelRequestRecord:
    attempt: int
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    finish_reason: str | None
    warning: str | None


@dataclass(frozen=True)
class InvalidOutputArtifact:
    phase: str
    attempt: int
    validation_stage: str
    validation_error: str
    finish_reason: str | None
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    response: str
    response_original_length: int
    response_truncated: bool
    correction_prompt: str | None
    correction_prompt_original_length: int | None
    correction_prompt_truncated: bool | None


class OpenAIProposer:
    """Bounded, schema-constrained Responses API adapter with no secret persistence."""

    def __init__(
        self,
        client: ResponsesClient | None = None,
        input_token_limit: int = 4096,
        output_token_limit: int = 1024,
        max_cost_usd: float = 1.0,
        total_cost_budget: CostBudget | None = None,
    ) -> None:
        self._client: ResponsesClient = (
            client if client is not None else cast(ResponsesClient, OpenAI().responses)
        )
        self._input_token_limit = input_token_limit
        self._output_token_limit = output_token_limit
        self._max_cost_usd = max_cost_usd
        self._total_cost_budget = total_cost_budget
        self.records: list[ModelRequestRecord] = []
        self._invalid_output_observer: Callable[[InvalidOutputArtifact], None] | None = None

    def set_invalid_output_observer(
        self, observer: Callable[[InvalidOutputArtifact], None] | None
    ) -> None:
        self._invalid_output_observer = observer

    def propose(self, prompt: str) -> CandidateProgram:
        return self._propose(prompt, phase="initial")

    def _propose(self, prompt: str, *, phase: str) -> CandidateProgram:
        request_prompt = _bounded_feedback(prompt)
        if _token_estimate(request_prompt) > self._input_token_limit:
            raise ModelOutputFailure("request input exceeds the configured token budget")
        for attempt in range(1, CORRECTION_ATTEMPTS + 2):
            reservation = self._reserve_request_cost()
            response = self._client.create(
                model=MODEL_NAME,
                reasoning={"effort": REASONING_EFFORT},
                input=request_prompt,
                max_output_tokens=self._output_token_limit,
                text={"format": {"type": "json_schema", **PROPOSAL_SCHEMA}},
            )
            self._record_usage(response, attempt, reservation)
            try:
                source = _proposal_source(response)
            except (AssertionError, KeyError, TypeError, ValueError) as error:
                validation_error = ProposalValidationError("schema", str(error))
            else:
                try:
                    _validate_dsl(source, _task_name_from_prompt(prompt))
                except Exception as error:
                    validation_error = ProposalValidationError("dsl", str(error))
                else:
                    return CandidateProgram(source=source, model_requests=attempt)
            correction_prompt = (
                None
                if attempt > CORRECTION_ATTEMPTS
                else _correction_prompt(prompt, _response_candidate(response), validation_error)
            )
            self._observe_invalid_output(
                response, attempt, validation_error, correction_prompt, phase
            )
            if attempt > CORRECTION_ATTEMPTS:
                raise ModelOutputFailure(
                    "model output failed schema or DSL validation"
                ) from validation_error
            assert correction_prompt is not None
            request_prompt = correction_prompt
        raise AssertionError("unreachable")

    def repair(self, prompt: str) -> CandidateProgram:
        """Propose a replacement under the same task-specific DSL contract."""
        task_name = _task_name_from_prompt(prompt)
        if task_name is None:
            raise ModelOutputFailure("repair prompt does not identify a supported task")
        bounded_context = _bounded_feedback(prompt, limit=5000)
        return self._propose(
            f"{task_prompt_for_repair(task_name)}\n"
            "Repair context (bounded evaluation evidence): " f"{bounded_context}",
            phase="repair",
        )

    def _reserve_request_cost(self) -> float | None:
        if self._total_cost_budget is None:
            return None
        return self._total_cost_budget.reserve(
            _estimated_cost_usd(self._input_token_limit, self._output_token_limit)
        )

    def _record_usage(self, response: object, attempt: int, reservation: float | None) -> None:
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0))
        output_tokens = int(getattr(usage, "output_tokens", 0))
        details = getattr(usage, "input_tokens_details", None)
        cached_tokens = int(getattr(details, "cached_tokens", 0))
        if input_tokens > self._input_token_limit or output_tokens > self._output_token_limit:
            raise ModelOutputFailure("model request exceeds the configured token budget")
        used_tokens = input_tokens + output_tokens
        cost_usd = _estimated_cost_usd(input_tokens, output_tokens)
        if cost_usd > self._max_cost_usd:
            raise ModelOutputFailure("model request exceeds the configured cost cap")
        if reservation is not None:
            assert self._total_cost_budget is not None
            self._total_cost_budget.settle(reservation, cost_usd)
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

    def _observe_invalid_output(
        self,
        response: object,
        attempt: int,
        validation_error: ProposalValidationError,
        correction_prompt: str | None,
        phase: str,
    ) -> None:
        if self._invalid_output_observer is None:
            return
        response_text = str(getattr(response, "output_text", ""))
        bounded_response, response_truncated = _redact_and_bound(response_text)
        bounded_prompt: str | None = None
        prompt_truncated: bool | None = None
        if correction_prompt is not None:
            bounded_prompt, prompt_truncated = _redact_and_bound(correction_prompt)
        record = self.records[-1]
        self._invalid_output_observer(
            InvalidOutputArtifact(
                phase=phase, attempt=attempt, validation_stage=validation_error.stage,
                validation_error=_redact_secrets(str(validation_error)),
                finish_reason=record.finish_reason,
                input_tokens=record.input_tokens, output_tokens=record.output_tokens,
                cached_tokens=record.cached_tokens, response=bounded_response,
                response_original_length=len(response_text.encode("utf-8")),
                response_truncated=response_truncated,
                correction_prompt=bounded_prompt,
                correction_prompt_original_length=(
                    len(correction_prompt.encode("utf-8"))
                    if correction_prompt is not None
                    else None
                ),
                correction_prompt_truncated=prompt_truncated,
            )
        )


def _proposal_source(response: object) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text is None:
        raise ValueError("response contains no output text")
    text = str(output_text).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    source = payload.get("source") if isinstance(payload, dict) else _code_fence_source(text)
    if not isinstance(source, str) or not source:
        raise ValueError("proposal source must be a non-empty string")
    return _normalize_source(source)


def _response_candidate(response: object) -> str:
    output_text = getattr(response, "output_text", "")
    text = str(output_text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("source"), str):
        text = payload["source"]
    return _bounded_feedback(text, limit=2000)


def _code_fence_source(text: str) -> str | None:
    match = re.fullmatch(r"\s*```(?:[A-Za-z0-9_-]+)?\s*\n?(.*?)\n?```\s*", text, re.DOTALL)
    return match.group(1) if match else None


def _normalize_source(source: str) -> str:
    return " ".join(source.strip().split())


def _validate_dsl(source: str, task_name: str | None = None) -> None:
    if task_name == "TextWorldPilot":
        from llm_gs.textworld_pilot import parse_program

        parse_program(source)
        return
    if task_name in {"DoorKey", "RedBlueDoor"}:
        MinigridDSL().parse_str_to_node(source)  # type: ignore[no-untyped-call]
        return
    if task_name in {"CleanHouse", "FourCorners"}:
        KarelDSL().parse_str_to_node(source)  # type: ignore[no-untyped-call]
        return
    try:
        KarelDSL().parse_str_to_node(source)  # type: ignore[no-untyped-call]
    except Exception:
        MinigridDSL().parse_str_to_node(source)  # type: ignore[no-untyped-call]


def _task_name_from_prompt(prompt: str) -> str | None:
    if "TextWorldPilot" in prompt:
        return "TextWorldPilot"
    if "DoorKey" in prompt:
        return "DoorKey"
    if "RedBlueDoor" in prompt:
        return "RedBlueDoor"
    if "CleanHouse" in prompt:
        return "CleanHouse"
    if "FourCorners" in prompt:
        return "FourCorners"
    return None


def task_prompt_for_repair(task_name: str) -> str:
    from llm_gs.manifest import task_prompt

    return task_prompt(task_name)


def _token_estimate(prompt: str) -> int:
    return (len(prompt.encode("utf-8")) + 3) // 4


def _estimated_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Conservative per-request ceiling used only to enforce an explicit client cap."""
    return input_tokens * 0.000_005 + output_tokens * 0.000_015


def _correction_prompt(
    original_prompt: str, candidate: str, validation_error: ProposalValidationError
) -> str:
    task_name = _task_name_from_prompt(original_prompt)
    contract = (
        task_prompt_for_repair(task_name)
        if task_name is not None
        else GENERIC_DSL_CONTRACT
    )
    error_class = validation_error.stage
    feedback = (
        "You are receiving an independent correction request. Do not rely on "
        "earlier API messages. Return only JSON matching the proposal schema.\n"
        f"Task contract: {contract}\n"
        f"Candidate program: {_bounded_feedback(candidate, limit=2000)}\n"
        f"Validation error ({error_class}): "
        f"{_bounded_feedback(str(validation_error), limit=1000)}\n"
        "Produce a complete replacement source; do not describe the correction."
    )
    return _bounded_feedback(feedback)


def _bounded_feedback(value: str, limit: int = FEEDBACK_LIMIT) -> str:
    redacted = _redact_secrets(value)
    if len(redacted) <= limit:
        return redacted
    marker = "\n...[TRIMMED]...\n"
    remaining = max(0, limit - len(marker))
    head = remaining // 2
    return redacted[:head] + marker + redacted[-(remaining - head):]


def _redact_secrets(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(
            lambda match: (
                f"{match.group(1)}[REDACTED]" if match.lastindex else "[REDACTED]"
            ),
            redacted,
        )
    for name, secret in os.environ.items():
        if secret and any(
            part in name.upper()
            for part in ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
        ):
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def _redact_and_bound(value: str) -> tuple[str, bool]:
    redacted = _redact_secrets(value)
    encoded = redacted.encode("utf-8")
    if len(encoded) <= INVALID_OUTPUT_CONTENT_LIMIT:
        return redacted, False
    return encoded[:INVALID_OUTPUT_CONTENT_LIMIT].decode("utf-8", errors="ignore"), True
