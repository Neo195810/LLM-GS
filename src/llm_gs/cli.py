from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

from pydantic import BaseModel

from llm_gs.execution import CleanHouseEvaluator, FakeOpenAIClient, OfflineEchoEvaluator, execute
from llm_gs.manifest import experiment_id, load_specification, resolve_manifest
from llm_gs.storage import WorkspaceStore


def _validate(args: argparse.Namespace) -> dict[str, object]:
    manifest = resolve_manifest(load_specification(args.specification))
    return {"experiment_id": experiment_id(manifest), "manifest": manifest}


def _run(args: argparse.Namespace) -> dict[str, object]:
    manifest = resolve_manifest(load_specification(args.specification))
    resolved_experiment_id = experiment_id(manifest)
    store = WorkspaceStore(args.workspace)
    execution_id = store.next_execution_id(resolved_experiment_id)
    report = execute(
        manifest,
        resolved_experiment_id,
        execution_id,
        FakeOpenAIClient(),
        CleanHouseEvaluator() if manifest.task["name"] == "CleanHouse" else OfflineEchoEvaluator(),
    )
    store.save(manifest, report)
    return {
        "execution_id": execution_id,
        "experiment_id": resolved_experiment_id,
        "status": report.status,
    }


def _report(args: argparse.Namespace) -> BaseModel:
    return WorkspaceStore(args.workspace).latest_report(args.experiment_id)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="llm-gs")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate")
    validate.add_argument("specification", type=Path)
    validate.set_defaults(handler=_validate)

    run = commands.add_parser("run")
    run.add_argument("specification", type=Path)
    run.add_argument("--workspace", type=Path, required=True)
    run.set_defaults(handler=_run)

    report = commands.add_parser("report")
    report.add_argument("--workspace", type=Path, required=True)
    report.add_argument("--experiment-id", required=True)
    report.set_defaults(handler=_report)
    return parser


def _fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def _serialize(output: object) -> object:
    if isinstance(output, BaseModel):
        return output.model_dump(mode="json")
    if isinstance(output, dict):
        return {key: _serialize(value) for key, value in output.items()}
    return output


def main() -> None:
    args = _parser().parse_args()
    handler: Callable[[argparse.Namespace], object] = args.handler
    try:
        output = handler(args)
    except ValueError as error:
        _fail(str(error))
    print(json.dumps(_serialize(output), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
