from __future__ import annotations

import argparse
import json
import sqlite3
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
from llm_gs.proposer import ModelOutputFailure, OpenAIProposer
from llm_gs.storage import WorkspaceStore


def _validate(args: argparse.Namespace) -> dict[str, object]:
    manifest = resolve_manifest(load_specification(args.specification))
    return {"experiment_id": experiment_id(manifest), "manifest": manifest}


def _run(args: argparse.Namespace) -> dict[str, object]:
    manifest = resolve_manifest(load_specification(args.specification))
    resolved_experiment_id = experiment_id(manifest)
    store = WorkspaceStore(args.workspace)
    try:
        report, status = execute_resumable(
            manifest,
            resolved_experiment_id,
            store,
            _model_client(args),
            CleanHouseEvaluator()
            if manifest.task["name"] == "CleanHouse"
            else OfflineEchoEvaluator(),
            args.stop_after,
        )
    except ModelOutputFailure as error:
        store.record_execution_failure(
            resolved_experiment_id,
            store.active_execution_id(resolved_experiment_id),
            "model_output",
            str(error),
        )
        raise
    except (OSError, sqlite3.Error) as error:
        store.record_execution_failure(
            resolved_experiment_id,
            store.active_execution_id(resolved_experiment_id),
            "infrastructure",
            str(error),
        )
        raise ValueError(f"infrastructure failure: {error}") from error
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
        _model_client(args),
        CleanHouseEvaluator() if manifest.task["name"] == "CleanHouse" else OfflineEchoEvaluator(),
    )
    return {
        "execution_id": report.execution_id if report else "",
        "experiment_id": args.experiment_id,
        "status": status,
    }


def _report(args: argparse.Namespace) -> dict[str, object]:
    return WorkspaceStore(args.workspace).reporting_view(args.experiment_id)


def _memory_build(args: argparse.Namespace) -> dict[str, object]:
    store = WorkspaceStore(args.workspace)
    entries = store.freeze_memory_snapshot(args.execution_id)
    return {
        "execution_id": args.execution_id,
        "memory_entries": len(entries),
        "snapshot_id": store.memory_snapshot_id(args.execution_id),
    }


def _inspect_attempt(args: argparse.Namespace) -> dict[str, object]:
    return WorkspaceStore(args.workspace).inspect_execution(args.execution_id)


def _export(args: argparse.Namespace) -> dict[str, str]:
    bundle = WorkspaceStore(args.workspace).export_bundle(args.experiment_id)
    args.output.write_text(json.dumps(bundle, sort_keys=True, indent=2), encoding="utf-8")
    return {"bundle": str(args.output), "checksum": str(bundle["checksum"])}


def _import(args: argparse.Namespace) -> dict[str, str]:
    try:
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read export bundle: {error}") from error
    if not isinstance(bundle, dict):
        raise ValueError("export bundle must be a JSON object")
    return {"experiment_id": WorkspaceStore(args.workspace).import_bundle(bundle)}


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
    run.add_argument("--enable-live-openai", action="store_true")
    run.add_argument("--max-cost-usd", type=float)
    run.set_defaults(handler=_run)

    resume = commands.add_parser("resume")
    resume.add_argument("--workspace", type=Path, required=True)
    resume.add_argument("--experiment-id", required=True)
    resume.add_argument("--enable-live-openai", action="store_true")
    resume.add_argument("--max-cost-usd", type=float)
    resume.set_defaults(handler=_resume)

    report = commands.add_parser("report")
    report.add_argument("--workspace", type=Path, required=True)
    report.add_argument("--experiment-id", required=True)
    report.set_defaults(handler=_report)

    memory = commands.add_parser("memory")
    memory_commands = memory.add_subparsers(dest="memory_command", required=True)
    memory_build = memory_commands.add_parser("build")
    memory_build.add_argument("--workspace", type=Path, required=True)
    memory_build.add_argument("--execution-id", required=True)
    memory_build.set_defaults(handler=_memory_build)

    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--workspace", type=Path, required=True)
    evaluate.add_argument("--experiment-id", required=True)
    evaluate.add_argument("--enable-live-openai", action="store_true")
    evaluate.add_argument("--max-cost-usd", type=float)
    evaluate.set_defaults(handler=_resume)

    inspect = commands.add_parser("inspect")
    inspect_commands = inspect.add_subparsers(dest="inspect_command", required=True)
    attempt = inspect_commands.add_parser("attempt")
    attempt.add_argument("--workspace", type=Path, required=True)
    attempt.add_argument("--execution-id", required=True)
    attempt.set_defaults(handler=_inspect_attempt)

    export = commands.add_parser("export")
    export.add_argument("--workspace", type=Path, required=True)
    export.add_argument("--experiment-id", required=True)
    export.add_argument("--output", type=Path, required=True)
    export.set_defaults(handler=_export)

    import_bundle = commands.add_parser("import")
    import_bundle.add_argument("--workspace", type=Path, required=True)
    import_bundle.add_argument("--bundle", type=Path, required=True)
    import_bundle.set_defaults(handler=_import)
    return parser


def _model_client(args: argparse.Namespace) -> FakeOpenAIClient | OpenAIProposer:
    if not args.enable_live_openai:
        return FakeOpenAIClient()
    if args.max_cost_usd is None or args.max_cost_usd <= 0:
        raise ValueError("live OpenAI requires a positive --max-cost-usd")
    return OpenAIProposer(max_cost_usd=args.max_cost_usd)


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
