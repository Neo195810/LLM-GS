# ruff: noqa: E501

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import httpx
import pytest
from openai import APITimeoutError

from llm_gs import cli
from llm_gs import proposer as proposer_module
from llm_gs.cli import _execute_with_failure_recording
from llm_gs.contracts import CandidateProgram, EpisodeResult, ExperimentSpecification
from llm_gs.execution import execute_resumable, reflect_once
from llm_gs.manifest import experiment_id, resolve_manifest, task_prompt
from llm_gs.proposer import (
    INVALID_OUTPUT_CONTENT_LIMIT,
    MODEL_NAME,
    REASONING_EFFORT,
    CostBudget,
    InvalidOutputArtifact,
    ModelOutputFailure,
    ModelPricing,
    ModelProgressEvent,
    OpenAIProposer,
    RequestNotSubmittedError,
)
from llm_gs.reflection import RepairCycle
from llm_gs.storage import WorkspaceStore, _bundle_checksum
from prog_policies.base.dsl import DSLParseError
from prog_policies.karel.dsl import KarelDSL
from prog_policies.minigrid.dsl import MinigridDSL


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
        output = self._outputs.pop(0)
        format_data = kwargs.get("text")
        if (
            isinstance(format_data, dict)
            and isinstance(format_data.get("format"), dict)
            and format_data["format"].get("name") == "candidate_program_v3"
        ):
            output = _pythonic_fixture(output)
        return SimpleNamespace(
            output_text=output, usage=self._usage, status="completed"
        )


def _pythonic_fixture(output: str) -> str:
    """Keep legacy valid DSL fixtures meaningful under the Pythonic response contract."""
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return output
    source = payload.get("source") if isinstance(payload, dict) else None
    actions = {
        "DEF run m( move m)": "move",
        "DEF run m( turnLeft m)": "turnLeft",
        "DEF run m( left m)": "left",
        "DEF run m( forward m)": "forward",
    }
    action = actions.get(source)
    if action is None:
        return output
    return json.dumps(
        {"python_source": f"def run():\n    {action}()\n", "dsl_backup": source}
    )


def test_openai_proposer_uses_pinned_structured_responses_request() -> None:
    responses = FakeResponses(['{"source":"DEF run m( turnLeft m)"}'])

    proposer = OpenAIProposer(responses)

    assert proposer.propose("make a program").source == "DEF run m( turnLeft m)"
    assert responses.calls[0]["model"] == MODEL_NAME
    assert responses.calls[0]["reasoning"] == {"effort": REASONING_EFFORT}
    assert responses.calls[0]["max_output_tokens"] == 4096
    assert responses.calls[0]["text"] == {
        "format": {
            "type": "json_schema",
            "name": "candidate_program_v2",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["source"],
                "properties": {
                    "source": {"type": "string", "minLength": 1, "maxLength": 2000}
                },
            },
        }
    }
    assert proposer.records[0].cached_tokens == 2


def test_openai_proposer_retries_one_timeout_and_records_each_attempt() -> None:
    class TimeoutThenSuccess:
        def __init__(self) -> None:
            self.calls = 0

        def create(self, **kwargs: object) -> object:
            _ = kwargs
            self.calls += 1
            if self.calls == 1:
                raise APITimeoutError(httpx.Request("POST", "https://api.openai.com/v1/responses"))
            return SimpleNamespace(
                output_text='{"source":"DEF run m( turnLeft m)"}',
                usage=SimpleNamespace(
                    input_tokens=10,
                    output_tokens=5,
                    input_tokens_details=SimpleNamespace(cached_tokens=2),
                ),
                status="completed",
            )

    responses = TimeoutThenSuccess()
    proposer = OpenAIProposer(responses)

    candidate = proposer.propose("make a program")

    assert candidate.model_requests == 2
    assert [(record.retry_layer, record.exception_type) for record in proposer.records] == [
        ("initial", "APITimeoutError"),
        ("request", None),
    ]
    assert all(record.duration_ms >= 0 for record in proposer.records)


def test_openai_proposer_reports_safe_progress_through_correction() -> None:
    events: list[ModelProgressEvent] = []
    proposer = OpenAIProposer(
        FakeResponses(["not json", '{"source":"DEF run m( turnLeft m)"}'])
    )
    proposer.set_progress_observer(events.append)

    proposer.propose("make a program")

    assert [(event.kind, event.correction_attempt) for event in events] == [
        ("request_started", 1),
        ("correction_requested", 1),
        ("request_started", 2),
        ("output_valid", 2),
    ]
    correction = events[1]
    assert correction.validation_stage == "schema"
    assert correction.detail == "proposal source must be a non-empty string"


def test_live_run_writes_model_progress_to_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    specification = tmp_path / "door-key.yaml"
    workspace = tmp_path / "workspace"
    specification.write_text(
        """\
spec_version: 1
display_name: progress
task:
  name: DoorKey
seeds:
  task: [7]
failure_strategy:
  name: regenerate
  max_repair_cycles: 1
""",
        encoding="utf-8",
    )
    model = OpenAIProposer(FakeResponses(["not json", "not json", "not json"]))
    monkeypatch.setattr(cli, "_model_client", lambda _: model)
    args = cli._parser().parse_args(
        [
            "run",
            str(specification),
            "--workspace",
            str(workspace),
            "--enable-live-openai",
            "--max-cost-usd",
            "1",
        ]
    )

    with pytest.raises(ValueError, match="model output failure"):
        args.handler(args)

    assert capsys.readouterr().err.splitlines() == [
        "[model] initial initial request -> requesting (provider attempt 1/2)",
        "[model] initial initial request -> output invalid "
        "(schema: Pythonic proposal must be a JSON object); requesting correction",
        "[model] initial correction 1/2 -> requesting (provider attempt 1/2)",
        "[model] initial correction 1/2 -> output invalid "
        "(schema: Pythonic proposal must be a JSON object); requesting correction",
        "[model] initial correction 2/2 -> requesting (provider attempt 1/2)",
        "[model] initial correction 2/2 -> output invalid "
        "(schema: Pythonic proposal must be a JSON object); corrections exhausted",
    ]
    assert model._progress_observer is None


def test_openai_proposer_uses_configured_model_name() -> None:
    responses = FakeResponses(['{"source":"DEF run m( turnLeft m)"}'])

    OpenAIProposer(
        responses,
        model_name="test-model",
        pricing=ModelPricing(0.000_001, 0.0, 0.000_002),
    ).propose("make a program")

    assert responses.calls[0]["model"] == "test-model"


def test_openai_proposer_corrects_invalid_output_at_most_twice() -> None:
    responses = FakeResponses(
        ["not json", '{"source":"not dsl"}', '{"source":"DEF run m( turnLeft m)"}']
    )

    candidate = OpenAIProposer(responses).propose("make a program")

    assert candidate.model_requests == 3
    assert len(responses.calls) == 3
    correction = str(responses.calls[1]["input"])
    assert "Validation error" in correction
    assert "Validation error (schema):" in correction
    assert "Candidate program" in correction
    assert "DEF run m(" in correction
    assert "Allowed actions:" in correction
    assert "previous_response_id" not in responses.calls[1]


@pytest.mark.parametrize(
    ("source", "task_name", "construct", "expected", "actual"),
    [
        ("DEF run x( move m)", "CleanHouse", "program wrapper", "`m(`", "x("),
        (
            "DEF run m( IFELSE c( frontIsClear c) i( move i) e( turnLeft e) m)",
            "CleanHouse",
            "IFELSE",
            "`ELSE`",
            "e(",
        ),
        (
            "DEF run m( REPEAT R=20 r( move r) m)",
            "CleanHouse",
            "REPEAT",
            "`R=<0-19>`",
            "R=20",
        ),
        (
            "DEF run m( IF c( front_object_type red h) c) i( forward i) m)",
            "DoorKey",
            "front_object_type",
            "`h(`",
            "red",
        ),
        ("DEF run m( mystery m)", "CleanHouse", "program", "known DSL symbol", "mystery"),
    ],
)
def test_dsl_validation_errors_are_actionable(
    source: str, task_name: str, construct: str, expected: str, actual: str
) -> None:
    with pytest.raises(DSLParseError) as raised:
        proposer_module._validate_dsl(source, task_name)

    error = raised.value
    assert error.construct == construct
    assert error.expected == expected
    assert error.actual == actual
    assert error.offset >= 0
    assert error.token_window


def test_openai_proposer_includes_bounded_python_diagnostic_in_correction_feedback() -> None:
    responses = FakeResponses(
        [
            (
                '{"python_source":"def run():\\n    pass\\n",'
                '"dsl_backup":"DEF run m( IF c( frontIsClear c) i( move"}'
            ),
            '{"source":"DEF run m( turnLeft m)"}',
        ]
    )

    candidate = OpenAIProposer(responses).propose("Solve CleanHouse")

    correction = str(responses.calls[1]["input"])
    assert candidate.model_requests == 2
    assert "run must contain at least one statement" in correction
    assert "Correction ordinal: 1 of 2." in correction
    assert len(correction) <= 8000


def test_repeated_invalid_output_changes_correction_feedback() -> None:
    invalid = '{"source":"DEF run m( REPEAT R=20 r( move r) m)"}'
    responses = FakeResponses([invalid, invalid, invalid])

    with pytest.raises(ModelOutputFailure, match="schema or DSL"):
        OpenAIProposer(responses).propose("Solve CleanHouse")

    first = str(responses.calls[1]["input"])
    second = str(responses.calls[2]["input"])
    assert first != second
    assert "Correction ordinal: 1 of 2." in first
    assert "Repeated invalid output: no." in first
    assert "Correction ordinal: 2 of 2." in second
    assert "Repeated invalid output: yes." in second


def test_repeated_invalid_output_recovers_after_warning() -> None:
    invalid = '{"source":"DEF run m( REPEAT R=20 r( move r) m)"}'
    valid = '{"source":"DEF run m( turnLeft m)"}'
    responses = FakeResponses([invalid, invalid, valid])

    candidate = OpenAIProposer(responses).propose("Solve CleanHouse")

    assert candidate.source == "DEF run m( turnLeft m)"
    assert candidate.model_requests == 3
    second = str(responses.calls[2]["input"])
    assert "Correction ordinal: 2 of 2." in second
    assert "Repeated invalid output: yes." in second


def test_minigrid_valid_control_flow_remains_accepted() -> None:
    proposer_module._validate_dsl(
        "DEF run m( IF c( and c( front_is_clear c) c( is_carrying_object c) c) "
        "i( forward i) m)",
        task_name="DoorKey",
    )


@pytest.mark.parametrize(
    "source",
    [
        "DEF run m( IF c( front_object_type h( red h) c) i( forward i) m)",
        "DEF run m( IF c( not c( front_object_color h( lava h) c) c) i( forward i) m)",
        (
            "DEF run m( IF c( and c( front_object_type h( red h) c) "
            "c( front_is_clear c) c) i( forward i) m)"
        ),
    ],
)
def test_minigrid_multitoken_feature_as_condition_remains_accepted(source: str) -> None:
    proposer_module._validate_dsl(source, task_name="DoorKey")


def test_minigrid_dsl_does_not_duplicate_the_base_parse_dispatch() -> None:
    assert MinigridDSL.parse_str_list_to_node is not None
    assert "parse_str_list_to_node" not in MinigridDSL.__dict__


def test_nested_boolean_expression_rejects_stranded_trailing_token() -> None:
    source = (
        "DEF run m( IF c( not c( frontIsClear c) frontIsClear c) i( move i) m)"
    )
    with pytest.raises(DSLParseError) as raised:
        KarelDSL().parse_str_to_node(source)

    error = raised.value
    assert error.construct == "not"
    assert error.expected == "`c)`"
    assert error.actual == "frontIsClear"


def test_nested_boolean_expression_rejected_with_assertions_disabled() -> None:
    source = "DEF run m( IF c( not c( frontIsClear c) frontIsClear c) i( move i) m)"
    with pytest.raises(DSLParseError):
        KarelDSL().parse_str_to_node(source)

    result = subprocess.run(
        [
            sys.executable,
            "-O",
            "-c",
            "from prog_policies.karel.dsl import KarelDSL\n"
            "from prog_policies.base.dsl import DSLParseError\n"
            f"source = {source!r}\n"
            "try:\n"
            "    KarelDSL().parse_str_to_node(source)\n"
            "except DSLParseError:\n"
            "    pass\n"
            "else:\n"
            "    raise SystemExit(1)\n",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_minigrid_malformed_feature_expression_is_rejected_with_assertions_disabled() -> None:
    source = "DEF run m( IF c( front_object_type h( red h) forward c) i( forward i) m)"
    with pytest.raises(DSLParseError, match="front_object_type"):
        MinigridDSL().parse_str_to_node(source)

    result = subprocess.run(
        [
            sys.executable,
            "-O",
            "-c",
            "from prog_policies.minigrid.dsl import MinigridDSL\n"
            "from prog_policies.base.dsl import DSLParseError\n"
            f"source = {source!r}\n"
            "try:\n"
            "    MinigridDSL().parse_str_to_node(source)\n"
            "except DSLParseError:\n"
            "    pass\n"
            "else:\n"
            "    raise SystemExit(1)\n",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


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
    assert artifact.validation_stage == "schema"
    assert artifact.finish_reason == "completed"
    assert artifact.response_original_length > len(artifact.response)
    assert "sk-response-secret" not in artifact.response
    assert "sk-response-secret" not in artifact.validation_error
    assert artifact.correction_prompt is not None
    assert "sk-prompt-secret" not in artifact.correction_prompt


@pytest.mark.parametrize(
    ("source", "evidence"),
    [
        ("def run():\n    mystery()\n", "mystery is not an allowed action"),
        ("def run():\n    move(1)\n", "action calls may not have arguments"),
    ],
)
def test_invalid_output_keeps_safe_dsl_symbols_while_redacting_credentials(
    source: str, evidence: str
) -> None:
    responses = FakeResponses(
        [
            json.dumps(
                {
                    "python_source": source,
                    "dsl_backup": "DEF run m( IF c( frontIsClear c) i( move",
                }
            ),
            '{"source":"DEF run m( turnLeft m)"}',
        ]
    )
    observed: list[InvalidOutputArtifact] = []
    proposer = OpenAIProposer(responses)
    proposer.set_invalid_output_observer(observed.append)

    candidate = proposer.propose("Solve CleanHouse with token: private-credential-value")

    assert candidate.model_requests == 2
    artifact = observed[0]
    assert evidence in artifact.validation_error
    assert artifact.correction_prompt is not None
    assert evidence in artifact.correction_prompt


def test_invalid_output_redacts_token_credential_from_artifact_fields() -> None:
    credential = "private-credential-value"
    responses = FakeResponses(
        [
            json.dumps({"source": f"not dsl token: {credential}"}),
            '{"source":"DEF run m( turnLeft m)"}',
        ]
    )
    observed: list[InvalidOutputArtifact] = []
    proposer = OpenAIProposer(responses)
    proposer.set_invalid_output_observer(observed.append)

    proposer.propose("Solve CleanHouse")

    artifact = observed[0]
    assert credential not in artifact.response
    assert credential not in artifact.validation_error
    assert artifact.correction_prompt is not None
    assert credential not in artifact.correction_prompt


def test_invalid_output_keeps_full_redacted_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detail = "parser failure sk-private-error " + "x" * 1_500

    def validate(source: str, task_name: str | None = None) -> None:
        _ = task_name
        if source == "DEF run m( move m)":
            raise ValueError(detail)

    monkeypatch.setattr(proposer_module, "_validate_dsl", validate)
    observed: list[InvalidOutputArtifact] = []
    proposer = OpenAIProposer(
        FakeResponses(
            [
                '{"python_source":"def run():\\n    move()\\n","dsl_backup":"DEF run m( move m)"}',
                '{"python_source":"def run():\\n    turnLeft()\\n","dsl_backup":"DEF run m( turnLeft m)"}',
            ]
        )
    )
    proposer.set_invalid_output_observer(observed.append)

    assert proposer.propose("Solve CleanHouse").source == "DEF run m( turnLeft m)"
    assert observed[0].validation_error == "parser failure sk-[REDACTED] " + "x" * 1_500


def test_openai_proposer_treats_incomplete_status_as_dedicated_schema_diagnostic() -> None:
    class IncompleteThenCompleteResponses:
        def __init__(self) -> None:
            self._outputs = ['{"source":"DEF run m( move', '{"source":"DEF run m( move m)"}']
            self._statuses = ["incomplete", "completed"]
            self.calls: list[dict[str, object]] = []
            self._usage = SimpleNamespace(
                input_tokens=10,
                output_tokens=5,
                input_tokens_details=SimpleNamespace(cached_tokens=0),
            )

        def create(self, **kwargs: object) -> object:
            self.calls.append(kwargs)
            return SimpleNamespace(
                output_text=self._outputs.pop(0),
                usage=self._usage,
                status=self._statuses.pop(0),
            )

    responses = IncompleteThenCompleteResponses()

    candidate = OpenAIProposer(cast(proposer_module.ResponsesClient, responses)).propose(
        "make a program"
    )

    assert candidate.source == "DEF run m( move m)"
    correction = str(responses.calls[1]["input"])
    assert "Validation error (schema):" in correction
    assert "incomplete" in correction
    assert "2,000 characters" in correction


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
    artifacts = cast(
        list[dict[str, object]],
        store.inspect_execution(report.execution_id)["invalid_output_artifacts"],
    )
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


def test_reports_and_exports_expose_only_safe_invalid_output_metadata(tmp_path: Path) -> None:
    manifest = resolve_manifest(
        ExperimentSpecification.model_validate(
            {
                "display_name": "private-invalid-output-observability",
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

    report, status = execute_resumable(
        manifest,
        experiment_id(manifest),
        store,
        OpenAIProposer(
            FakeResponses(
                [
                    '{"source":"DEF run m( raw-invalid-response-marker sk-report-secret)"}',
                    '{"source":"DEF run m( turnLeft m)"}',
                ]
            )
        ),
        SuccessfulEvaluator(),
    )

    assert report is not None
    assert status == "completed"
    audit = cast(list[dict[str, object]], store.inspect_execution(report.execution_id)["invalid_output_artifacts"])
    response_hash = str(audit[0]["response_hash"])
    prompt_hash = str(audit[0]["correction_prompt_hash"])
    private_response = (tmp_path / "artifacts" / response_hash.removeprefix("sha256:")).read_text()
    private_correction_prompt = (tmp_path / "artifacts" / prompt_hash.removeprefix("sha256:")).read_text()
    assert "raw-invalid-response-marker" in private_response
    assert "sk-report-secret" not in private_response
    assert "independent correction request" in private_correction_prompt

    reporting = store.reporting_view(experiment_id(manifest))
    bundle = store.export_bundle(experiment_id(manifest))
    observations = cast(dict[str, object], reporting["request_observations"])
    assert observations["attempts"] == 2
    assert observations["successful"] == 2
    assert observations["timeouts"] == 0
    assert observations["exception_types"] == {}
    assert observations["matrix_arm_retries"] == 0
    assert cast(dict[str, dict[str, int]], observations["retry_layers"])["initial"]["attempts"] == 2
    for public_output in (reporting, bundle):
        serialized = json.dumps(public_output, sort_keys=True)
        assert "raw-invalid-response-marker" not in serialized
        assert "independent correction request" not in serialized
        assert "sk-report-secret" not in serialized
    assert reporting["invalid_output"] == {
        "count": 1,
        "validation_stages": {"dsl": 1},
        "validation_errors": {"dsl_validation_failure": 1},
        "artifacts": [
            {**audit[0], "validation_error": "dsl_validation_failure"}
        ],
    }
    records = cast(dict[str, list[dict[str, object]]], bundle["records"])
    assert records["invalid_output_artifacts"] == [
        {
            "id": 1,
            "execution_id": report.execution_id,
            **audit[0],
            "validation_error": "dsl_validation_failure",
        }
    ]
    assert response_hash not in cast(dict[str, str], bundle["artifacts"])
    assert prompt_hash not in cast(dict[str, str], bundle["artifacts"])
    for version in (1, 2):
        legacy_bundle = json.loads(json.dumps(bundle))
        legacy_bundle["bundle_version"] = version
        legacy_records = cast(dict[str, object], legacy_bundle["records"])
        legacy_records.pop("invalid_output_artifacts")
        if version == 1:
            legacy_records.pop("matrix_arms")
        legacy_payload = {key: value for key, value in legacy_bundle.items() if key != "checksum"}
        legacy_bundle["checksum"] = _bundle_checksum(legacy_payload)
        assert WorkspaceStore(tmp_path / f"legacy-v{version}").import_bundle(legacy_bundle) == experiment_id(manifest)


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


def test_resumable_execution_persists_invalid_repair_output_before_success(
    tmp_path: Path,
) -> None:
    manifest = resolve_manifest(
        ExperimentSpecification.model_validate(
            {
                "display_name": "repair-invalid-output-observation",
                "task": {"name": "CleanHouse"},
                "seeds": {"task": [1]},
                "failure_strategy": {"name": "reflect", "max_repair_cycles": 1},
            }
        )
    )
    store = WorkspaceStore(tmp_path)

    class RepairingEvaluator:
        def evaluate(self, candidate: CandidateProgram, task_seed: int) -> EpisodeResult:
            _ = task_seed
            if candidate.source == "DEF run m( move m)":
                return EpisodeResult(outcome="success")
            return EpisodeResult(
                outcome="partial_completion",
                failure_type="stalled",
                failure_reason="initial candidate stalled",
                evaluation_evidence={"reason": "initial candidate stalled"},
            )

    report, status = execute_resumable(
        manifest,
        experiment_id(manifest),
        store,
        OpenAIProposer(
            FakeResponses(
                [
                    '{"source":"DEF run m( turnLeft m)"}',
                    '{"source":"not dsl"}',
                    '{"source":"DEF run m( move m)"}',
                ]
            )
        ),
        RepairingEvaluator(),
    )

    assert report is not None
    assert status == "completed"
    artifacts = cast(
        list[dict[str, object]],
        store.inspect_execution(report.execution_id)["invalid_output_artifacts"],
    )
    assert [(artifact["phase"], artifact["attempt"]) for artifact in artifacts] == [
        ("repair", 1)
    ]


def test_resumable_execution_persists_terminal_invalid_repair_outputs(
    tmp_path: Path,
) -> None:
    manifest = resolve_manifest(
        ExperimentSpecification.model_validate(
            {
                "display_name": "terminal-repair-invalid-output-observation",
                "task": {"name": "CleanHouse"},
                "seeds": {"task": [1]},
                "failure_strategy": {"name": "reflect", "max_repair_cycles": 1},
            }
        )
    )
    store = WorkspaceStore(tmp_path)

    class FailingEvaluator:
        def evaluate(self, candidate: CandidateProgram, task_seed: int) -> EpisodeResult:
            _ = candidate, task_seed
            return EpisodeResult(
                outcome="partial_completion",
                failure_type="stalled",
                failure_reason="candidate stalled",
                evaluation_evidence={"reason": "candidate stalled"},
            )

    with pytest.raises(ModelOutputFailure, match="schema or DSL"):
        execute_resumable(
            manifest,
            experiment_id(manifest),
            store,
            OpenAIProposer(
                FakeResponses(['{"source":"DEF run m( turnLeft m)"}', "", "", ""])
            ),
            FailingEvaluator(),
        )

    execution_id = store.active_execution_id(experiment_id(manifest))
    assert execution_id is not None
    artifacts = cast(
        list[dict[str, object]],
        store.inspect_execution(execution_id)["invalid_output_artifacts"],
    )
    assert [(artifact["phase"], artifact["attempt"]) for artifact in artifacts] == [
        ("repair", 1),
        ("repair", 2),
        ("repair", 3),
    ]


def test_frozen_memory_protocol_samples_independent_candidates_per_population_member(
    tmp_path: Path,
) -> None:
    manifest = resolve_manifest(
        ExperimentSpecification.model_validate(
            {
                "display_name": "population-search",
                "task": {"name": "CleanHouse"},
                "seed_suite": {
                    "version": 1,
                    "memory_training": [1],
                    "development": [2],
                    "held_out": [3],
                },
                "search_strategy": {"name": "cem", "population_size": 2, "elite_count": 1},
                "failure_strategy": {"name": "reflect", "max_repair_cycles": 1},
            }
        )
    )
    store = WorkspaceStore(tmp_path)

    class DistinguishableModel:
        def __init__(self) -> None:
            self.propose_sources = [
                "DEF run m( turnLeft m)",  # dedicated Memory Snapshot proposal
                "DEF run m( turnRight m)",  # population member 0's development candidate
                "DEF run m( turnLeft turnLeft m)",  # population member 1's development candidate
            ]
            self.repair_sources = [
                "DEF run m( move m)",  # member 0's own repair
                "DEF run m( move move m)",  # member 1's own repair
            ]
            self.propose_calls = 0
            self.repair_prompts: list[str] = []

        def propose(self, prompt: str) -> CandidateProgram:
            _ = prompt
            self.propose_calls += 1
            return CandidateProgram(source=self.propose_sources.pop(0))

        def repair(self, prompt: str) -> CandidateProgram:
            self.repair_prompts.append(prompt)
            return CandidateProgram(source=self.repair_sources.pop(0))

    model = DistinguishableModel()

    class ScriptedEvaluator:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def evaluate(self, candidate: CandidateProgram, task_seed: int) -> EpisodeResult:
            self.calls.append((candidate.source, task_seed))
            if candidate.source in {"DEF run m( move m)", "DEF run m( move move m)"}:
                return EpisodeResult(outcome="success")
            return EpisodeResult(
                outcome="partial_completion",
                failure_type="stalled",
                failure_reason=f"{candidate.source} stalled",
                evaluation_evidence={"initial_marker_count": 3, "remaining_marker_count": 2},
            )

    evaluator = ScriptedEvaluator()

    report, status = execute_resumable(manifest, experiment_id(manifest), store, model, evaluator)

    assert status == "completed"
    assert report is not None
    protocol = cast(dict[str, object], report.audit["frozen_memory_protocol"])
    secondary_metrics = cast(dict[str, object], protocol["secondary_metrics"])
    assert secondary_metrics["population_size"] == 2
    # Each population member independently runs its own Repair Cycle.
    assert secondary_metrics["total_repair_attempts"] == 2
    assert secondary_metrics["development_candidate_count"] == 4
    assert model.propose_calls == 3
    assert len(model.repair_prompts) == 2
    assert "DEF run m( turnRight m) stalled" in model.repair_prompts[0]
    assert "DEF run m( turnLeft turnLeft m) stalled" in model.repair_prompts[1]

    # The Memory Snapshot proposal is independent of the population's
    # development-search candidates: it alone answers the memory_training
    # seed, and never reappears against the development seed.
    memory_training_calls = [call for call in evaluator.calls if call[1] == 1]
    development_calls = [call for call in evaluator.calls if call[1] == 2]
    held_out_calls = [call for call in evaluator.calls if call[1] == 3]
    assert memory_training_calls == [("DEF run m( turnLeft m)", 1)]
    assert {source for source, _ in development_calls} == {
        "DEF run m( turnRight m)",
        "DEF run m( move m)",
        "DEF run m( turnLeft turnLeft m)",
        "DEF run m( move move m)",
    }
    assert len(development_calls) == 4
    assert len(held_out_calls) == 1


def test_frozen_memory_protocol_single_candidate_population_is_byte_identical(
    tmp_path: Path,
) -> None:
    manifest = resolve_manifest(
        ExperimentSpecification.model_validate(
            {
                "display_name": "single-candidate-population",
                "task": {"name": "CleanHouse"},
                "seed_suite": {
                    "version": 1,
                    "memory_training": [1],
                    "development": [2],
                    "held_out": [3],
                },
                "failure_strategy": {"name": "reflect", "max_repair_cycles": 1},
            }
        )
    )
    store = WorkspaceStore(tmp_path)

    class SingleCallModel:
        def __init__(self) -> None:
            self.propose_calls = 0

        def propose(self, prompt: str) -> CandidateProgram:
            _ = prompt
            self.propose_calls += 1
            return CandidateProgram(source="DEF run m( turnLeft m)")

        def repair(self, prompt: str) -> CandidateProgram:
            _ = prompt
            return CandidateProgram(source="DEF run m( move m)")

    model = SingleCallModel()

    class ScriptedEvaluator:
        def evaluate(self, candidate: CandidateProgram, task_seed: int) -> EpisodeResult:
            _ = task_seed
            if candidate.source == "DEF run m( move m)":
                return EpisodeResult(outcome="success")
            return EpisodeResult(
                outcome="partial_completion",
                failure_type="stalled",
                failure_reason="candidate stalled",
                evaluation_evidence={"initial_marker_count": 3, "remaining_marker_count": 2},
            )

    report, status = execute_resumable(
        manifest, experiment_id(manifest), store, model, ScriptedEvaluator()
    )

    assert status == "completed"
    assert report is not None
    protocol = cast(dict[str, object], report.audit["frozen_memory_protocol"])
    secondary_metrics = cast(dict[str, object], protocol["secondary_metrics"])
    assert secondary_metrics["population_size"] == 1
    assert secondary_metrics["total_repair_attempts"] == 1
    assert secondary_metrics["development_candidate_count"] == 2
    # A population of exactly one reuses the dedicated Memory Snapshot
    # proposal as its sole development candidate: one propose() call total.
    assert model.propose_calls == 1


def test_invalid_repair_artifact_persistence_failure_surfaces_immediately(
    tmp_path: Path,
) -> None:
    class FailingArtifactStore(WorkspaceStore):
        def save_invalid_output_artifact(self, execution_id: str, artifact: object) -> None:
            _ = execution_id, artifact
            raise sqlite3.OperationalError("artifact storage unavailable")

    store = FailingArtifactStore(tmp_path)

    with pytest.raises(sqlite3.OperationalError, match="artifact storage unavailable"):
        reflect_once(
            CandidateProgram(source="DEF run m( turnLeft m)"),
            EpisodeResult(
                outcome="partial_completion",
                failure_type="stalled",
                failure_reason="candidate stalled",
                evaluation_evidence={"reason": "candidate stalled"},
            ),
            OpenAIProposer(FakeResponses(['{"source":"not dsl"}'])),
            RepairCycle(task_name="CleanHouse"),
            "exec_000001",
            store,
            "Repair CleanHouse using evidence",
        )


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
    assert "Actions: move" in repair_prompt
    assert "sk-secret-value" not in repair_prompt


def test_invalid_repair_retry_keeps_evidence_in_an_independent_request() -> None:
    responses = FakeResponses(
        ['{"source":"not dsl"}', '{"source":"DEF run m( move m)"}']
    )

    OpenAIProposer(responses).repair(
        "Repair CleanHouse using evidence: candidate stalled after Actions: move"
    )

    correction = str(responses.calls[1]["input"])
    assert "Bounded evaluation evidence:" in correction
    assert "candidate stalled after Actions: move" in correction
    assert "Goal: collect every marker" in correction
    assert "Candidate program: not dsl" in correction
    assert "previous_response_id" not in responses.calls[1]


def test_openai_proposer_observes_invalid_repair_output_before_successful_correction() -> None:
    responses = FakeResponses(
        ['{"source":"not dsl"}', '{"source":"DEF run m( move m)"}']
    )
    observed: list[InvalidOutputArtifact] = []
    proposer = OpenAIProposer(responses)
    proposer.set_invalid_output_observer(observed.append)

    candidate = proposer.repair("Repair CleanHouse using evidence")

    assert candidate.model_requests == 2
    assert len(observed) == 1
    assert observed[0].phase == "repair"
    assert observed[0].attempt == 1
    assert observed[0].correction_prompt is not None


def test_openai_proposer_observes_terminal_empty_repair_outputs() -> None:
    observed: list[InvalidOutputArtifact] = []
    proposer = OpenAIProposer(FakeResponses(["", "", ""]))
    proposer.set_invalid_output_observer(observed.append)

    with pytest.raises(ModelOutputFailure, match="schema or DSL"):
        proposer.repair("Repair CleanHouse using evidence")

    assert [(artifact.phase, artifact.attempt) for artifact in observed] == [
        ("repair", 1),
        ("repair", 2),
        ("repair", 3),
    ]
    assert observed[-1].correction_prompt is None


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
    assert "Goal: collect every marker" in str(responses.calls[0]["input"])
    assert "for _ in range(<integer 0..19>)" in str(responses.calls[0]["input"])


def test_openai_proposer_blocks_input_before_sending_a_request() -> None:
    responses = FakeResponses(['{"source":"DEF run m( turnLeft m)"}'])

    with pytest.raises(ModelOutputFailure, match="input exceeds"):
        OpenAIProposer(responses, input_token_limit=1).propose("this prompt is too large")
    assert responses.calls == []


def test_openai_proposer_enforces_shared_total_cost_cap() -> None:
    budget = CostBudget(0.005)
    responses = FakeResponses(['{"source":"DEF run m( turnLeft m)"}'])

    with pytest.raises(ModelOutputFailure, match="total cost cap"):
        OpenAIProposer(responses, total_cost_budget=budget).propose("make a program")
    assert responses.calls == []


def test_openai_proposer_settles_actual_usage_with_independent_cached_pricing() -> None:
    budget = CostBudget(0.006)
    pricing = ModelPricing(0.000_000_2, 0.000_000_1, 0.000_001_2)
    proposer = OpenAIProposer(
        FakeResponses(['{"source":"DEF run m( turnLeft m)"}'], input_tokens=10, output_tokens=5),
        total_cost_budget=budget,
        pricing=pricing,
    )

    proposer.propose("make a program")

    assert proposer.records[0].cost_usd == pytest.approx(0.000_007_8)
    assert budget.summary() == {
        "cap_usd": 0.006,
        "reserved_usd": 0.0,
        "settled_usd": pytest.approx(0.000_007_8),
        "unknown_usd": 0.0,
        "remaining_usd": pytest.approx(0.005_992_2),
        "input_tokens": 10,
        "cached_tokens": 2,
        "output_tokens": 5,
    }


def test_openai_proposer_keeps_unknown_reservation_when_response_has_no_usage() -> None:
    class MissingUsageResponses:
        def create(self, **kwargs: object) -> object:
            _ = kwargs
            return SimpleNamespace(
                output_text='{"source":"DEF run m( turnLeft m)"}', usage=None, status="completed"
            )

    budget = CostBudget(0.01)
    proposer = OpenAIProposer(MissingUsageResponses(), total_cost_budget=budget)

    proposer.propose("make a program")

    assert proposer.records[0].cost_state == "unknown"
    assert budget.summary()["unknown_usd"] == pytest.approx(0.005_734_4)


def test_openai_proposer_releases_reservation_only_when_transport_confirms_no_submission() -> None:
    class UnsentResponses:
        def create(self, **kwargs: object) -> object:
            _ = kwargs
            raise RequestNotSubmittedError("not sent")

    budget = CostBudget(0.01)
    proposer = OpenAIProposer(UnsentResponses(), total_cost_budget=budget)

    with pytest.raises(RequestNotSubmittedError, match="not sent"):
        proposer.propose("make a program")

    assert proposer.records[0].cost_state == "not_submitted"
    assert proposer.records[0].exception_type == "RequestNotSubmittedError"
    assert budget.summary()["remaining_usd"] == 0.01


def test_openai_proposer_marks_invalid_usage_as_unknown() -> None:
    class InvalidUsageResponses:
        def create(self, **kwargs: object) -> object:
            _ = kwargs
            return SimpleNamespace(
                output_text='{"source":"DEF run m( turnLeft m)"}',
                usage=SimpleNamespace(
                    input_tokens=1,
                    output_tokens=1,
                    input_tokens_details=SimpleNamespace(cached_tokens=2),
                ),
                status="completed",
            )

    budget = CostBudget(0.01)
    proposer = OpenAIProposer(InvalidUsageResponses(), total_cost_budget=budget)

    with pytest.raises(ModelOutputFailure, match="invalid usage"):
        proposer.propose("make a program")

    assert proposer.records[0].cost_state == "unknown"
    assert budget.summary()["unknown_usd"] == pytest.approx(0.005_734_4)


@pytest.mark.parametrize(
    ("task_name", "goal", "task_condition"),
    [
        ("CleanHouse", "collect every marker", "markersPresent"),
        ("FourCorners", "four corner cells and nowhere else", "putMarker"),
        ("DoorKey", "pick up the key, unlock the door, then reach the goal", "is_carrying_object"),
        (
            "RedBlueDoor",
            "red door before opening the blue door",
            "front_object_color",
        ),
    ],
)
def test_task_prompt_includes_goal_and_pythonic_contract(
    task_name: str, goal: str, task_condition: str
) -> None:
    prompt = task_prompt(task_name)

    assert "python_source" in prompt
    assert "dsl_backup" in prompt
    assert "def run():" in prompt
    assert "for _ in range(<integer 0..19>)" in prompt
    assert goal in prompt
    assert task_condition in prompt
    assert "2,000 characters" in prompt
    assert "No imports" in prompt


@pytest.mark.parametrize(
    ("task_name", "dsl"),
    [
        ("CleanHouse", KarelDSL()),
        ("FourCorners", KarelDSL()),
        ("DoorKey", MinigridDSL()),
        ("RedBlueDoor", MinigridDSL()),
    ],
)
def test_task_prompt_describes_restricted_python_control_flow(
    task_name: str, dsl: KarelDSL | MinigridDSL
) -> None:
    prompt = task_prompt(task_name)
    _ = dsl
    assert "if/else" in prompt
    assert "predicate-guarded while" in prompt
