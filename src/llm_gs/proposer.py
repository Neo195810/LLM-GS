from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol, cast

from openai import OpenAI

from llm_gs.contracts import CandidateProgram
from prog_policies.karel.dsl import KarelDSL
from prog_policies.minigrid.dsl import MinigridDSL

MODEL_NAME = "gpt-5.6-luna"
REASONING_EFFORT = "medium"
PROPOSAL_SCHEMA_VERSION = 2
PROPOSAL_SOURCE_CHAR_LIMIT = 2000
PROPOSAL_SCHEMA = {
    "name": "candidate_program_v2",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["source"],
        "properties": {
            "source": {
                "type": "string",
                "minLength": 1,
                "maxLength": PROPOSAL_SOURCE_CHAR_LIMIT,
            }
        },
    },
}
CORRECTION_ATTEMPTS = 2
FEEDBACK_LIMIT = 8000
INVALID_OUTPUT_CONTENT_LIMIT = 64 * 1024
GENERIC_DSL_CONTRACT = (
    "Task name is unspecified. Return JSON with only source. Use exact DSL syntax "
    "DEF run m( <statements> m), and use only actions valid for the identified "
    "task. Allowed actions: move, turnLeft, turnRight, pickMarker, putMarker, "
    "left, right, forward, pickup, drop, toggle. Source must be no more than "
    "2,000 characters. Never output pseudocode, Markdown, or Python."
)
INCOMPLETE_RESPONSE_DIAGNOSTIC = (
    "response was incomplete (provider status: incomplete). Return one complete "
    "JSON object matching the proposal schema: shorten the source to well under "
    "2,000 characters and reduce control-flow nesting depth so the full response "
    "fits in the output-token budget."
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


class RequestNotSubmittedError(Exception):
    """A transport can prove a reserved request never reached the API."""


class ProposalValidationError(ValueError):
    """A candidate failed schema extraction or task DSL validation."""

    def __init__(self, stage: str, detail: str) -> None:
        self.stage = stage
        super().__init__(detail)


@dataclass(frozen=True)
class ModelPricing:
    input_usd_per_token: float
    cached_input_usd_per_token: float
    output_usd_per_token: float


MODEL_PRICING = {
    MODEL_NAME: ModelPricing(
        input_usd_per_token=0.000_000_2,
        cached_input_usd_per_token=0.000_000_2,
        output_usd_per_token=0.000_001_2,
    )
}


class CostBudget:
    """Shared dollar cap with settled, reserved, and unknown usage separated."""

    def __init__(self, max_cost_usd: float) -> None:
        self.max_cost_usd = max_cost_usd
        self.reserved_cost_usd = 0.0
        self.settled_cost_usd = 0.0
        self.unknown_cost_usd = 0.0
        self.input_tokens = 0
        self.cached_tokens = 0
        self.output_tokens = 0

    @property
    def used_cost_usd(self) -> float:
        return self.reserved_cost_usd + self.settled_cost_usd + self.unknown_cost_usd

    def reserve(self, maximum_cost_usd: float) -> float:
        if self.used_cost_usd + maximum_cost_usd > self.max_cost_usd:
            raise ModelOutputFailure("model request exceeds the configured total cost cap")
        self.reserved_cost_usd += maximum_cost_usd
        return maximum_cost_usd

    def settle(
        self,
        reserved_cost_usd: float,
        actual_cost_usd: float,
        input_tokens: int,
        cached_tokens: int,
        output_tokens: int,
    ) -> None:
        self.reserved_cost_usd -= reserved_cost_usd
        self.settled_cost_usd += actual_cost_usd
        self.input_tokens += input_tokens
        self.cached_tokens += cached_tokens
        self.output_tokens += output_tokens

    def mark_unknown(self, reserved_cost_usd: float) -> None:
        self.reserved_cost_usd -= reserved_cost_usd
        self.unknown_cost_usd += reserved_cost_usd

    def release(self, reserved_cost_usd: float) -> None:
        self.reserved_cost_usd -= reserved_cost_usd

    def summary(self) -> dict[str, float | int]:
        return {
            "cap_usd": self.max_cost_usd,
            "reserved_usd": self.reserved_cost_usd,
            "settled_usd": self.settled_cost_usd,
            "unknown_usd": self.unknown_cost_usd,
            "remaining_usd": self.max_cost_usd - self.used_cost_usd,
            "input_tokens": self.input_tokens,
            "cached_tokens": self.cached_tokens,
            "output_tokens": self.output_tokens,
        }


@dataclass(frozen=True)
class ModelRequestRecord:
    attempt: int
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    finish_reason: str | None
    warning: str | None
    cost_usd: float
    cost_state: str


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
        output_token_limit: int = 4096,
        max_cost_usd: float = 1.0,
        total_cost_budget: CostBudget | None = None,
        pricing: ModelPricing | None = None,
        model_name: str = MODEL_NAME,
    ) -> None:
        self._client: ResponsesClient = (
            client if client is not None else cast(ResponsesClient, OpenAI().responses)
        )
        self._input_token_limit = input_token_limit
        self._output_token_limit = output_token_limit
        self._max_cost_usd = max_cost_usd
        self._total_cost_budget = total_cost_budget
        self._model_name = model_name
        self._pricing = pricing if pricing is not None else MODEL_PRICING[model_name]
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
        invalid_fingerprints: set[str] = set()
        for attempt in range(1, CORRECTION_ATTEMPTS + 2):
            reservation = self._reserve_request_cost()
            try:
                response = self._client.create(
                    model=self._model_name,
                    reasoning={"effort": REASONING_EFFORT},
                    input=request_prompt,
                    max_output_tokens=self._output_token_limit,
                    text={"format": {"type": "json_schema", **PROPOSAL_SCHEMA}},
                )
            except RequestNotSubmittedError:
                self._release_reservation(reservation)
                raise
            except Exception:
                self._record_unknown_request(attempt, reservation)
                raise
            self._record_usage(response, attempt, reservation)
            if getattr(response, "status", None) == "incomplete":
                validation_error = ProposalValidationError(
                    "schema", INCOMPLETE_RESPONSE_DIAGNOSTIC
                )
            else:
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
            candidate = _response_candidate(response)
            fingerprint = sha256(
                _normalize_source(_response_candidate_raw(response)).encode("utf-8")
            ).hexdigest()
            repeated_output = fingerprint in invalid_fingerprints
            invalid_fingerprints.add(fingerprint)
            correction_prompt = (
                None
                if attempt > CORRECTION_ATTEMPTS
                else _correction_prompt(
                    prompt,
                    candidate,
                    validation_error,
                    correction_ordinal=attempt,
                    repeated_output=repeated_output,
                )
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
            _estimated_cost_usd(
                self._input_token_limit, 0, self._output_token_limit, self._pricing
            )
        )

    def _record_usage(self, response: object, attempt: int, reservation: float | None) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            self._record_unknown_request(attempt, reservation, getattr(response, "status", None))
            return
        try:
            input_tokens = int(usage.input_tokens)
            output_tokens = int(usage.output_tokens)
            details = getattr(usage, "input_tokens_details", None)
            cached_tokens = int(getattr(details, "cached_tokens", 0))
            if min(input_tokens, output_tokens, cached_tokens) < 0:
                raise ValueError("model response reports negative token usage")
            if cached_tokens > input_tokens:
                raise ValueError("model response reports more cached than input tokens")
        except (AttributeError, TypeError, ValueError) as error:
            self._record_unknown_request(attempt, reservation, getattr(response, "status", None))
            raise ModelOutputFailure("model response contains invalid usage") from error
        used_tokens = input_tokens + output_tokens
        cost_usd = _estimated_cost_usd(
            input_tokens, cached_tokens, output_tokens, self._pricing
        )
        if reservation is not None:
            assert self._total_cost_budget is not None
            self._total_cost_budget.settle(
                reservation, cost_usd, input_tokens, cached_tokens, output_tokens
            )
        total_limit = self._input_token_limit + self._output_token_limit
        warning = "token_budget_80_percent" if used_tokens * 100 >= total_limit * 80 else None
        self.records.append(
            ModelRequestRecord(
                attempt=self._next_record_attempt(),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_tokens=cached_tokens,
                finish_reason=getattr(response, "status", None),
                warning=warning,
                cost_usd=cost_usd,
                cost_state="settled",
            )
        )
        if input_tokens > self._input_token_limit or output_tokens > self._output_token_limit:
            raise ModelOutputFailure("model request exceeds the configured token budget")
        if cost_usd > self._max_cost_usd:
            raise ModelOutputFailure("model request exceeds the configured cost cap")

    def _record_unknown_request(
        self, attempt: int, reservation: float | None, finish_reason: object = None
    ) -> None:
        cost_usd = reservation or 0.0
        if reservation is not None:
            assert self._total_cost_budget is not None
            self._total_cost_budget.mark_unknown(reservation)
        self.records.append(
            ModelRequestRecord(
                attempt=self._next_record_attempt(),
                input_tokens=0,
                output_tokens=0,
                cached_tokens=0,
                finish_reason=finish_reason if isinstance(finish_reason, str) else None,
                warning=None,
                cost_usd=cost_usd,
                cost_state="unknown",
            )
        )

    def _next_record_attempt(self) -> int:
        return len(self.records) + 1

    def _release_reservation(self, reservation: float | None) -> None:
        if reservation is not None:
            assert self._total_cost_budget is not None
            self._total_cost_budget.release(reservation)

    def cost_summary(self) -> dict[str, float | int]:
        settled = [record for record in self.records if record.cost_state == "settled"]
        unknown = [record for record in self.records if record.cost_state == "unknown"]
        return {
            "reserved_usd": 0.0,
            "settled_usd": sum(record.cost_usd for record in settled),
            "unknown_usd": sum(record.cost_usd for record in unknown),
            "input_tokens": sum(record.input_tokens for record in settled),
            "cached_tokens": sum(record.cached_tokens for record in settled),
            "output_tokens": sum(record.output_tokens for record in settled),
        }

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


def _response_candidate_raw(response: object) -> str:
    output_text = getattr(response, "output_text", "")
    text = str(output_text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("source"), str):
        text = payload["source"]
    return text


def _response_candidate(response: object) -> str:
    return _bounded_feedback(_response_candidate_raw(response), limit=2000)


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


def _estimated_cost_usd(
    input_tokens: int, cached_tokens: int, output_tokens: int, pricing: ModelPricing
) -> float:
    """Price actual usage; reservations substitute input/output limits for usage."""
    return (
        (input_tokens - cached_tokens) * pricing.input_usd_per_token
        + cached_tokens * pricing.cached_input_usd_per_token
        + output_tokens * pricing.output_usd_per_token
    )


def _correction_prompt(
    original_prompt: str,
    candidate: str,
    validation_error: ProposalValidationError,
    *,
    correction_ordinal: int,
    repeated_output: bool,
) -> str:
    task_name = _task_name_from_prompt(original_prompt)
    contract = (
        task_prompt_for_repair(task_name)
        if task_name is not None
        else GENERIC_DSL_CONTRACT
    )
    error_class = validation_error.stage
    repeated_feedback = (
        "Repeated invalid output: yes. Return a structurally different complete replacement.\n"
        if repeated_output
        else "Repeated invalid output: no.\n"
    )
    feedback = (
        "You are receiving an independent correction request. Do not rely on "
        "earlier API messages. Return only JSON matching the proposal schema.\n"
        f"Task contract: {contract}\n"
        f"Candidate program: {_bounded_feedback(candidate, limit=2000)}\n"
        f"Validation error ({error_class}): "
        f"{_bounded_feedback(str(validation_error), limit=1000)}\n"
        f"Correction ordinal: {correction_ordinal} of {CORRECTION_ATTEMPTS}.\n"
        f"{repeated_feedback}"
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
