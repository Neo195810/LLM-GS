from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

from openai import APIError
from pydantic import BaseModel

from llm_gs.contracts import ExperimentManifest, ExperimentReport
from llm_gs.execution import (
    CleanHouseEvaluator,
    DoorKeyEvaluator,
    FakeOpenAIClient,
    FourCornersEvaluator,
    OfflineEchoEvaluator,
    RedBlueDoorEvaluator,
    TextWorldPilotEvaluator,
    execute_resumable,
)
from llm_gs.manifest import (
    experiment_id,
    load_ablation_matrix_specification,
    load_specification,
    resolve_manifest,
)
from llm_gs.matrix import build_matrix_manifests, matrix_report
from llm_gs.proposer import CostBudget, ModelOutputFailure, OpenAIProposer
from llm_gs.storage import WorkspaceStore
from llm_gs.textworld_release_gate import evaluate_release_gate, evidence_from_dict


def _validate(args: argparse.Namespace) -> dict[str, object]:
    manifest = resolve_manifest(load_specification(args.specification))
    return {"experiment_id": experiment_id(manifest), "manifest": manifest}


def _run(args: argparse.Namespace) -> dict[str, object]:
    manifest = resolve_manifest(load_specification(args.specification))
    resolved_experiment_id = experiment_id(manifest)
    store = WorkspaceStore(args.workspace)
    report, status = _execute_with_failure_recording(
        manifest, resolved_experiment_id, store, args, args.stop_after
    )
    return {
        "execution_id": report.execution_id
        if report
        else store.active_execution_id(resolved_experiment_id),
        "experiment_id": resolved_experiment_id,
        "status": status,
    }


def _execute_with_failure_recording(
    manifest: ExperimentManifest,
    experiment_id: str,
    store: WorkspaceStore,
    args: argparse.Namespace,
    stop_after: int | None = None,
    model: FakeOpenAIClient | OpenAIProposer | None = None,
) -> tuple[ExperimentReport | None, str]:
    try:
        report, status = execute_resumable(
            manifest,
            experiment_id,
            store,
            model if model is not None else _model_client(args),
            CleanHouseEvaluator()
            if manifest.task["name"] == "CleanHouse"
            else DoorKeyEvaluator()
            if manifest.task["name"] == "DoorKey"
            else RedBlueDoorEvaluator()
            if manifest.task["name"] == "RedBlueDoor"
            else FourCornersEvaluator()
            if manifest.task["name"] == "FourCorners"
            else TextWorldPilotEvaluator()
            if manifest.task["name"] == "TextWorldPilot"
            else OfflineEchoEvaluator(),
            stop_after,
        )
    except ModelOutputFailure as error:
        failure_kind = "budget" if "cost cap" in str(error) else "model_output"
        store.record_execution_failure(
            experiment_id,
            store.active_execution_id(experiment_id),
            failure_kind,
            str(error),
        )
        raise ValueError(f"model output failure: {error}") from error
    except (APIError, OSError, sqlite3.Error, TimeoutError) as error:
        store.record_execution_failure(
            experiment_id,
            store.active_execution_id(experiment_id),
            "infrastructure",
            str(error),
        )
        raise ValueError(f"infrastructure failure: {error}") from error
    return report, status


def _resume(args: argparse.Namespace) -> dict[str, object]:
    store = WorkspaceStore(args.workspace)
    manifest = store.manifest(args.experiment_id)
    report, status = _execute_with_failure_recording(manifest, args.experiment_id, store, args)
    return {
        "execution_id": report.execution_id if report else "",
        "experiment_id": args.experiment_id,
        "status": status,
    }


def _report(args: argparse.Namespace) -> dict[str, object]:
    return WorkspaceStore(args.workspace).reporting_view(args.experiment_id)


def _textworld_promote(args: argparse.Namespace) -> dict[str, object]:
    try:
        payload = json.loads(args.evidence.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid TextWorld release evidence: {error}") from error
    gate = evaluate_release_gate(evidence_from_dict(payload))
    if not gate.passed:
        raise ValueError(
            "TextWorld formal promotion blocked: " + ", ".join(gate.unmet_requirements)
        )
    return {"passed": gate.passed, "unmet_requirements": list(gate.unmet_requirements)}


def _matrix_validate(args: argparse.Namespace) -> dict[str, object]:
    manifests = build_matrix_manifests(load_ablation_matrix_specification(args.specification))
    return {
        "arms": [
            {"experiment_id": experiment_id(manifest), "manifest": manifest}
            for manifest in manifests
        ]
    }


def _matrix_run(args: argparse.Namespace) -> dict[str, object]:
    manifests = build_matrix_manifests(load_ablation_matrix_specification(args.specification))
    store = WorkspaceStore(args.workspace)
    reports = []
    total_cost_budget = (
        CostBudget(args.max_total_cost_usd)
        if args.enable_live_openai and args.max_total_cost_usd is not None
        else None
    )
    for manifest in manifests:
        store.register_matrix_arm(manifest, experiment_id(manifest))
    for manifest in manifests:
        resolved_experiment_id = experiment_id(manifest)
        previous_failed_execution = store.latest_failed_execution_id(resolved_experiment_id)
        for infrastructure_retry in range(3):
            store.set_matrix_arm_state(resolved_experiment_id, "running")
            try:
                report, _ = _execute_with_failure_recording(
                    manifest,
                    resolved_experiment_id,
                    store,
                    args,
                    model=_model_client(args, total_cost_budget=total_cost_budget),
                )
                if report is None:
                    raise ValueError("matrix arm did not produce a completed report")
                if previous_failed_execution is not None:
                    store.record_replacement_execution(
                        resolved_experiment_id,
                        previous_failed_execution,
                        report.execution_id,
                    )
                store.set_matrix_arm_state(resolved_experiment_id, "completed")
                break
            except Exception as error:
                state, error_class = _matrix_arm_failure(error)
                failed_execution = store.active_execution_id(resolved_experiment_id)
                if error_class == "execution":
                    store.record_execution_failure(
                        resolved_experiment_id,
                        failed_execution,
                        "infrastructure",
                        str(error),
                    )
                    error_class = "infrastructure"
                if failed_execution is not None:
                    store.mark_execution_failed(failed_execution)
                if error_class == "infrastructure":
                    if failed_execution is not None:
                        if previous_failed_execution is not None:
                            store.record_replacement_execution(
                                resolved_experiment_id,
                                previous_failed_execution,
                                failed_execution,
                            )
                        previous_failed_execution = failed_execution
                    if infrastructure_retry < 2:
                        continue
                    state = "infrastructure-failed"
                store.set_matrix_arm_state(resolved_experiment_id, state, error_class, str(error))
                break
        reports.append(store.reporting_view(resolved_experiment_id))
    output = matrix_report(reports)
    if total_cost_budget is not None:
        output["cost"] = {
            "cap_usd": total_cost_budget.max_cost_usd,
            "used_usd": total_cost_budget.used_cost_usd,
        }
    return output


def _matrix_report(args: argparse.Namespace) -> dict[str, object]:
    manifests = build_matrix_manifests(load_ablation_matrix_specification(args.specification))
    store = WorkspaceStore(args.workspace)
    for manifest in manifests:
        store.register_matrix_arm(manifest, experiment_id(manifest))
    reports = []
    for manifest in manifests:
        resolved_experiment_id = experiment_id(manifest)
        reports.append(store.reporting_view(resolved_experiment_id))
    return matrix_report(reports)


def _matrix_arm_failure(error: Exception) -> tuple[str, str]:
    if "cost cap" in str(error):
        return "blocked-by-budget", "budget"
    if isinstance(error.__cause__, ModelOutputFailure) or str(error).startswith(
        "model output failure:"
    ):
        return "model-output-failed", "model_output"
    if str(error).startswith("infrastructure failure:"):
        return "infrastructure-failed", "infrastructure"
    return "infrastructure-failed", "execution"


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

    textworld = commands.add_parser("textworld")
    textworld_commands = textworld.add_subparsers(dest="textworld_command", required=True)
    textworld_promote = textworld_commands.add_parser("promote")
    textworld_promote.add_argument(
        "--evidence",
        type=Path,
        required=True,
        help="persisted JSON artifact containing formal TextWorld release evidence",
    )
    textworld_promote.set_defaults(handler=_textworld_promote)

    matrix = commands.add_parser("matrix")
    matrix_commands = matrix.add_subparsers(dest="matrix_command", required=True)
    matrix_validate = matrix_commands.add_parser("validate")
    matrix_validate.add_argument("specification", type=Path)
    matrix_validate.set_defaults(handler=_matrix_validate)
    matrix_run = matrix_commands.add_parser("run")
    matrix_run.add_argument("specification", type=Path)
    matrix_run.add_argument("--workspace", type=Path, required=True)
    matrix_run.add_argument("--enable-live-openai", action="store_true")
    matrix_run.add_argument("--max-cost-usd", type=float)
    matrix_run.add_argument("--max-total-cost-usd", type=float)
    matrix_run.set_defaults(handler=_matrix_run)
    matrix_report_command = matrix_commands.add_parser("report")
    matrix_report_command.add_argument("specification", type=Path)
    matrix_report_command.add_argument("--workspace", type=Path, required=True)
    matrix_report_command.set_defaults(handler=_matrix_report)

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


def _model_client(
    args: argparse.Namespace, total_cost_budget: CostBudget | None = None
) -> FakeOpenAIClient | OpenAIProposer:
    if not args.enable_live_openai:
        return FakeOpenAIClient()
    if args.max_cost_usd is None or args.max_cost_usd <= 0:
        raise ValueError("live OpenAI requires a positive --max-cost-usd")
    return OpenAIProposer(
        max_cost_usd=args.max_cost_usd, total_cost_budget=total_cost_budget
    )


def _fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def _serialize(output: object) -> object:
    if isinstance(output, BaseModel):
        return _serialize(output.model_dump(mode="json"))
    if isinstance(output, dict):
        return {key: _serialize(value) for key, value in output.items()}
    if isinstance(output, list):
        return [_serialize(value) for value in output]
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
