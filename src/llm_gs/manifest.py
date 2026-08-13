from __future__ import annotations

import hashlib
import json
import platform
from importlib.metadata import version
from pathlib import Path

import yaml
from pydantic import ValidationError

from llm_gs.contracts import ExperimentManifest, ExperimentSpecification

OFFLINE_PROMPT = "Produce one deterministic offline candidate."
CLEAN_HOUSE_PROMPT = "Produce one deterministic CleanHouse DSL candidate."


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_bytes(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _source_identity() -> str:
    digest = hashlib.sha256()
    source_root = Path(__file__).resolve().parent
    for path in sorted(source_root.glob("*.py")):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def _dependency_identity() -> str:
    lockfile = _project_root() / "uv.lock"
    if not lockfile.is_file():
        raise ValueError("uv.lock is required to resolve dependency identity")
    return sha256_bytes(lockfile.read_bytes())


def load_specification(path: Path) -> ExperimentSpecification:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"cannot read experiment specification: {error}") from error
    if not isinstance(raw, dict):
        raise ValueError("experiment specification must be a YAML mapping")
    try:
        return ExperimentSpecification.model_validate(raw)
    except ValidationError as error:
        raise ValueError(str(error)) from error


def resolve_manifest(specification: ExperimentSpecification) -> ExperimentManifest:
    is_clean_house = specification.task.name == "CleanHouse"
    return ExperimentManifest(
        code={"source_sha256": _source_identity()},
        dependencies={"uv_lock_sha256": _dependency_identity()},
        components={
            "evaluator": "v1-clean-house-adapter-v1" if is_clean_house else "offline-echo-v1",
            "proposer": "fake-openai-v1",
            "reporter": "deterministic-json-v1",
        },
        contracts={
            "parser": "karel-dsl-v1" if is_clean_house else "offline-dsl-v1",
            "prompt_sha256": sha256_bytes(
                (CLEAN_HOUSE_PROMPT if is_clean_house else OFFLINE_PROMPT).encode("utf-8")
            ).removeprefix("sha256:"),
            **({"outcome_classifier": "clean-house-v1"} if is_clean_house else {}),
        },
        runtime={
            "package": "llm-gs-v2",
            "package_version": version("llm-gs-v2"),
            "python": platform.python_version(),
        },
        model={
            "client": "fake",
            "max_output_tokens": 1024,
            "model": "fake-openai-v1",
            "reasoning_effort": "medium",
        },
        task={
            "adapter_version": 1,
            "name": specification.task.name,
            **({"outcome_classifier_version": 1} if is_clean_house else {}),
        },
        search_strategy={"name": "single_candidate", "seed": specification.seeds.search},
        failure_strategy=specification.failure_strategy.model_dump(mode="json"),
        budgets={
            "episode_evaluations": 1,
            "input_tokens": 4096,
            "model_requests": 1,
            "output_tokens": 1024,
        },
        memory_snapshot={"id": "none", "read_only": True},
        specification=specification.model_dump(mode="json", exclude={"display_name"}),
    )


def experiment_id(manifest: ExperimentManifest) -> str:
    payload = canonical_json(manifest.model_dump(mode="json")).encode("ascii")
    return f"exp_{hashlib.sha256(payload).hexdigest()}"
