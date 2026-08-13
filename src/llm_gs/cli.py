from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

from pydantic import BaseModel

from llm_gs.execution import (
    CleanHouseEvaluator,
    FakeOpenAIClient,
    OfflineEchoEvaluator,
    execute_resumable,
)
from llm_gs.manifest import experiment_id, load_specification, resolve_manifest
from llm_gs.storage import WorkspaceStore


def _validate(args: argparse.Namespace) -> dict[str, object]:
    manifest = resolve_manifest(load_specification(args.specification))
    return {"experiment_id": experiment_id(manifest), "manifest": manifest}


def _run(args: argparse.Namespace) -> dict[str, object]:
    manifest = resolve_manifest(load_specification(args.specification))
    resolved_experiment_id = experiment_id(manifest)
    store = WorkspaceStore(args.workspace)
    report, status = execute_resumable(
        manifest,
        resolved_experiment_id,
        store,
        FakeOpenAIClient(),
        CleanHouseEvaluator() if manifest.task["name"] == "CleanHouse" else OfflineEchoEvaluator(),
        args.stop_after,
    )
    return {
        "execution_id": report.execution_id
        if report
        else store.active_execution_id(resolved_experiment_id),
        "experiment_id": resolved_experiment_id,
        "status": status,
    }


def _resume(args: argparse.Namespace) -> dict[str, object]:
    store = WorkspaceStore(args.workspace)
    manifest = store.manifest(args.experiment_id)
    report, status = execute_resumable(
        manifest,
        args.experiment_id,
        store,
        FakeOpenAIClient(),
        CleanHouseEvaluator() if manifest.task["name"] == "CleanHouse" else OfflineEchoEvaluator(),
    )
    return {
        "execution_id": report.execution_id if report else "",
        "experiment_id": args.experiment_id,
        "status": status,
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
    run.add_argument("--stop-after", type=int)
    run.set_defaults(handler=_run)

    resume = commands.add_parser("resume")
    resume.add_argument("--workspace", type=Path, required=True)
    resume.add_argument("--experiment-id", required=True)
    resume.set_defaults(handler=_resume)

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
