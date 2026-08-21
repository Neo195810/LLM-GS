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


def test_invalid_pythonic_source_does_not_admit_backup_in_ticket_one() -> None:
    payload = json.dumps(
        {
            "python_source": "def run():\n    import os\n",
            "dsl_backup": "DEF run m( move m)",
        }
    )

    with pytest.raises(ModelOutputFailure, match="schema or DSL validation"):
        OpenAIProposer(_Responses(payload)).propose(task_prompt("CleanHouse"))


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
    assert "proposal_protocol" not in direct.contracts
    assert "python_translator" not in direct.contracts
    assert experiment_id(pythonic) != experiment_id(direct)
