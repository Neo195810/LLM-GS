from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from llm_gs.contracts import ExperimentSpecification
from llm_gs.manifest import experiment_id, resolve_manifest, task_prompt
from llm_gs.proposer import (
    ModelOutputFailure,
    OpenAIProposer,
    lower_pythonic_dsl,
    normalize_dsl_backup,
    proposal_contract,
)
from prog_policies.karel.dsl import KarelDSL
from prog_policies.minigrid.dsl import MinigridDSL


class _Responses:
    def __init__(self, output: str) -> None:
        self.output = output
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_text=self.output,
            usage=SimpleNamespace(
                input_tokens=1,
                output_tokens=1,
                input_tokens_details=SimpleNamespace(cached_tokens=0),
            ),
            status="completed",
        )


def test_karel_pythonic_source_lowers_to_canonical_dsl() -> None:
    source = """\
def run():
    move()
    if frontIsClear():
        turnLeft()
    else:
        turnRight()
    while markersPresent():
        pickMarker()
    for _ in range(3):
        putMarker()
"""

    lowered = lower_pythonic_dsl(source, "CleanHouse")

    assert lowered == (
        "DEF run m( move IFELSE c( frontIsClear c) i( turnLeft i) ELSE e( turnRight e) "
        "WHILE c( markersPresent c) w( pickMarker w) REPEAT R=3 r( putMarker r) m)"
    )
    KarelDSL().parse_str_to_node(lowered)


def test_minigrid_pythonic_source_lowers_to_canonical_dsl() -> None:
    source = """\
def run():
    if front_object_type("door"):
        toggle()
    while front_is_clear():
        forward()
"""

    lowered = lower_pythonic_dsl(source, "DoorKey")

    assert lowered == (
        "DEF run m( IF c( front_object_type h( door h) c) i( toggle i) "
        "WHILE c( front_is_clear c) w( forward w) m)"
    )
    MinigridDSL().parse_str_to_node(lowered)


def test_pythonic_source_allows_nested_if_in_else_block() -> None:
    source = """\
def run():
    if frontIsClear():
        move()
    else:
        if markersPresent():
            pickMarker()
        else:
            turnLeft()
"""

    lowered = lower_pythonic_dsl(source, "CleanHouse")

    assert lowered == (
        "DEF run m( IFELSE c( frontIsClear c) i( move i) ELSE e( "
        "IFELSE c( markersPresent c) i( pickMarker i) ELSE e( turnLeft e) e) m)"
    )
    KarelDSL().parse_str_to_node(lowered)


@pytest.mark.parametrize(
    "source",
    [
        "import os\ndef run():\n    move()\n",
        "def run(value):\n    move()\n",
        "def run():\n    count = 1\n    move()\n",
        "def run():\n    for _ in range(20):\n        move()\n",
        "def run():\n    if True:\n        move()\n",
        "def run():\n    while frontIsClear() and markersPresent():\n        move()\n",
        "def run():\n    if frontIsClear(1):\n        move()\n",
        (
            "def run():\n    if frontIsClear():\n        move()\n"
            "    elif markersPresent():\n        move()\n"
        ),
        "def run():\n    mystery()\n",
    ],
)
def test_pythonic_source_rejects_disallowed_or_invalid_constructs(source: str) -> None:
    with pytest.raises(ValueError):
        lower_pythonic_dsl(source, "CleanHouse")


def test_pythonic_contract_uses_bounded_pair_and_python_precedence() -> None:
    payload = json.dumps(
        {
            "python_source": "def run():\n    move()\n",
            "dsl_backup": "DEF run m( turnLeft m)",
        }
    )
    responses = _Responses(payload)

    candidate = OpenAIProposer(responses).propose(task_prompt("CleanHouse"))

    assert candidate.source == "DEF run m( move m)"
    assert responses.calls[0]["text"] == {
        "format": {"type": "json_schema", **proposal_contract("CleanHouse").schema}
    }


def test_invalid_pythonic_source_admits_valid_backup() -> None:
    payload = json.dumps(
        {
            "python_source": "def run():\n    import os\n",
            "dsl_backup": "DEF run m( move m)",
        }
    )

    candidate = OpenAIProposer(_Responses(payload)).propose(task_prompt("CleanHouse"))

    assert candidate.source == "DEF run m( move m)"


@pytest.mark.parametrize(
    ("backup", "task_name", "expected"),
    [
        ("```\nDEF run m( move m)\n```", "CleanHouse", "DEF run m( move m)"),
        (" DEF   run m(  move()  m) ", "CleanHouse", "DEF run m( move m)"),
        ("DEF run m( move", "CleanHouse", "DEF run m( move m)"),
        ("DEF run m( forward() m)", "DoorKey", "DEF run m( forward m)"),
    ],
)
def test_normalize_dsl_backup_admits_only_documented_formatting(
    backup: str, task_name: str, expected: str
) -> None:
    assert normalize_dsl_backup(backup, task_name) == expected


@pytest.mark.parametrize(
    "backup",
    [
        "DEF run m( IF c( frontIsClear c) i( move",
        "DEF run m( WHILE c( True c) w( move w) m)",
        "DEF run m( REPEAT R=20 r( move r) m)",
    ],
)
def test_normalize_dsl_backup_rejects_semantic_or_ambiguous_repairs(backup: str) -> None:
    with pytest.raises(ValueError):
        normalize_dsl_backup(backup, "CleanHouse")


def test_pythonic_correction_includes_pair_and_dual_admission_diagnostics() -> None:
    invalid = json.dumps(
        {
            "python_source": "def run():\n    import os\n",
            "dsl_backup": "DEF run m( IF c( frontIsClear c) i( move",
        }
    )
    valid = json.dumps(
        {
            "python_source": "def run():\n    move()\n",
            "dsl_backup": "DEF run m( move m)",
        }
    )
    class _SequentialResponses(_Responses):
        def __init__(self) -> None:
            super().__init__(invalid)
            self.outputs = [invalid, valid]

        def create(self, **kwargs: object) -> object:
            self.calls.append(kwargs)
            self.output = self.outputs.pop(0)
            return SimpleNamespace(
                output_text=self.output,
                usage=SimpleNamespace(
                    input_tokens=1,
                    output_tokens=1,
                    input_tokens_details=SimpleNamespace(cached_tokens=0),
                ),
                status="completed",
            )

    responses = _SequentialResponses()
    candidate = OpenAIProposer(responses).propose(task_prompt("CleanHouse"))

    correction = str(responses.calls[1]["input"])
    assert candidate.source == "DEF run m( move m)"
    assert "Python source:" in correction
    assert "DSL backup:" in correction
    assert "Python admission error:" in correction
    assert "Backup DSL admission error:" in correction


def test_pythonic_repetition_uses_normalized_complete_proposal_pair() -> None:
    first = json.dumps(
        {
            "python_source": "def run():\n    import os\n",
            "dsl_backup": "```\nDEF run m( move() mystery m)\n```",
        }
    )
    normalized = json.dumps(
        {
            "python_source": "def run(): import os",
            "dsl_backup": "DEF run m( move mystery m)",
        }
    )

    class _RepeatedResponses(_Responses):
        def __init__(self) -> None:
            super().__init__(first)
            self.outputs = [first, normalized, normalized]

        def create(self, **kwargs: object) -> object:
            self.calls.append(kwargs)
            self.output = self.outputs.pop(0)
            return SimpleNamespace(
                output_text=self.output,
                usage=SimpleNamespace(
                    input_tokens=1,
                    output_tokens=1,
                    input_tokens_details=SimpleNamespace(cached_tokens=0),
                ),
                status="completed",
            )

    responses = _RepeatedResponses()

    with pytest.raises(ModelOutputFailure, match="schema or DSL validation"):
        OpenAIProposer(responses).propose(task_prompt("CleanHouse"))

    assert "Repeated invalid output: yes." in str(responses.calls[2]["input"])


def test_direct_dsl_contract_is_preserved_for_textworld_and_offline() -> None:
    assert proposal_contract("TextWorldPilot").protocol == "direct-dsl-v2"
    assert proposal_contract("offline.echo").schema["schema"]["required"] == ["source"]


def test_pythonic_manifest_identity_is_distinct_and_legacy_contracts_remain_direct() -> None:
    base = {
        "display_name": "proposal-protocol",
        "seeds": {"task": [1], "search": 2, "replicate": 3},
        "failure_strategy": {"name": "regenerate", "max_repair_cycles": 0},
    }
    pythonic = resolve_manifest(
        ExperimentSpecification.model_validate({**base, "task": {"name": "CleanHouse"}})
    )
    direct = resolve_manifest(
        ExperimentSpecification.model_validate({**base, "task": {"name": "TextWorldPilot"}})
    )

    assert pythonic.contracts["proposal_protocol"] == "pythonic-dsl-v1"
    assert pythonic.contracts["proposal_schema_version"] == "v3"
    assert pythonic.contracts["python_translator"] == "pythonic-dsl-translator-v1"
    assert pythonic.contracts["backup_normalizer"] == "conservative-backup-normalizer-v1"
    assert "proposal_protocol" not in direct.contracts
    assert "python_translator" not in direct.contracts
    assert experiment_id(pythonic) != experiment_id(direct)
