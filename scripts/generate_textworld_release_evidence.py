"""Generate real, persisted TextWorld pilot formal-promotion evidence.

Runs 100 seeds through the TextWorld pilot adapter in two independent
Python processes each (replay determinism), measures real single- and
batch-episode latency and peak memory in a fresh process, and records the
structured evidence classes the release gate requires. Writes the resulting
JSON artifact for `llm-gs textworld promote --evidence <artifact.json>`.
"""

from __future__ import annotations

import json
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PYTHON = str(_ROOT / ".venv" / "bin" / "python")
_WORKER = _ROOT / "scripts" / "textworld_evidence_worker.py"
_SEEDS = range(100)

_SUCCESS_SOURCE = (
    "WHEN not_has_key DO take_key; WHEN has_key DO unlock_chest; "
    "WHEN chest_unlocked DO open_chest"
)
_INVALID_ACTION_SOURCE = "WHEN not_has_key DO open_chest"
_UNSATISFIED_PRECONDITION_SOURCE = "WHEN chest_open DO take_key"


def _run_worker(seed: int, process_id: str, source: str = _SUCCESS_SOURCE) -> dict[str, object]:
    completed = subprocess.run(
        [_PYTHON, str(_WORKER), str(seed), process_id, source],
        check=True,
        capture_output=True,
        text=True,
        cwd=_ROOT,
    )
    payload: dict[str, object] = json.loads(completed.stdout)
    return payload


def _collect_replay_artifacts() -> list[dict[str, object]]:
    artifacts: list[dict[str, object]] = []
    for seed in _SEEDS:
        first = _run_worker(seed, "process-a")
        second = _run_worker(seed, "process-b")
        replay_keys = ("terminal_state", "evidence_sha256", "score", "action_count")
        if any(first[key] != second[key] for key in replay_keys):
            raise RuntimeError(f"cross-process replay mismatch at seed {seed}: {first} != {second}")
        for record in (first, second):
            artifacts.append(
                {
                    "seed": record["seed"],
                    "process_id": record["process_id"],
                    "terminal_state": record["terminal_state"],
                    "evidence_sha256": record["evidence_sha256"],
                    "score": record["score"],
                    "action_count": record["action_count"],
                }
            )
    return artifacts


def _collect_evidence_records() -> list[dict[str, str]]:
    success = _run_worker(0, "process-evidence", _SUCCESS_SOURCE)
    invalid_action = _run_worker(0, "process-evidence", _INVALID_ACTION_SOURCE)
    unsatisfied = _run_worker(0, "process-evidence", _UNSATISFIED_PRECONDITION_SOURCE)
    assert success["outcome"] == "success", success
    assert invalid_action["failure_reason"] == "invalid_action", invalid_action
    assert unsatisfied["failure_reason"] == "quest_incomplete", unsatisfied
    return [
        {
            "name": "success",
            "status": "observed",
            "detail": (
                f"seed 0, source={_SUCCESS_SOURCE!r} won with "
                f"terminal_state sha256={success['evidence_sha256']}"
            ),
        },
        {
            "name": "invalid_action",
            "status": "observed",
            "detail": (
                f"seed 0, source={_INVALID_ACTION_SOURCE!r} attempted 'open chest' "
                "while locked; adapter set failure_reason=invalid_action "
                f"(terminal_state sha256={invalid_action['evidence_sha256']})"
            ),
        },
        {
            "name": "unsatisfied_precondition",
            "status": "observed",
            "detail": (
                f"seed 0, source={_UNSATISFIED_PRECONDITION_SOURCE!r} rule predicate "
                "never held so no action ran; adapter set "
                f"failure_reason=quest_incomplete (sha256={unsatisfied['evidence_sha256']})"
            ),
        },
        {
            "name": "timeout",
            "status": "not_applicable",
            "detail": (
                "TextWorldPilotAdapter.evaluate bounds every episode to "
                "limits.max_actions (<=3) with no wall-clock deadline in the "
                "adapter or textworld.start(); there is no timeout code path "
                "to observe (src/llm_gs/textworld_pilot.py:66-129)."
            ),
        },
        {
            "name": "runtime_error",
            "status": "not_applicable",
            "detail": (
                "parse_program() rejects any source outside the fixed DSL "
                "grammar before TextWorldPilotAdapter.evaluate() runs "
                "(src/llm_gs/textworld_pilot.py:43-56), and the proposer's "
                "_validate_dsl() rejects malformed candidates even earlier, "
                "so no engine-side runtime error is reachable during evaluate()."
            ),
        },
    ]


def _measure_single_episode_p95_ms(repetitions: int = 20) -> float:
    timings_ms: list[float] = []
    for repetition in range(repetitions):
        start = time.perf_counter()
        _run_worker(repetition, "process-single-timing")
        timings_ms.append((time.perf_counter() - start) * 1000.0)
    return _p95(timings_ms)


def _measure_batch_episode_p95_ms_and_peak_memory(
    repetitions: int = 20,
) -> tuple[float, float]:
    script = (
        "import json, resource, sys, time\n"
        "from llm_gs.contracts import CandidateProgram\n"
        "from llm_gs.textworld_pilot import TextWorldPilotAdapter, TextWorldPilotLimits\n"
        "adapter = TextWorldPilotAdapter()\n"
        f"candidate = CandidateProgram(source={_SUCCESS_SOURCE!r})\n"
        "timings = []\n"
        f"for seed in range({repetitions}):\n"
        "    start = time.perf_counter()\n"
        "    adapter.evaluate(candidate, seed=seed, limits=TextWorldPilotLimits(max_actions=3))\n"
        "    timings.append((time.perf_counter() - start) * 1000.0)\n"
        "peak_kb_or_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss\n"
        "print(json.dumps({'timings_ms': timings, 'peak_ru_maxrss': peak_kb_or_bytes}))\n"
    )
    completed = subprocess.run(
        [_PYTHON, "-c", script], check=True, capture_output=True, text=True, cwd=_ROOT
    )
    payload = json.loads(completed.stdout)
    peak_raw = payload["peak_ru_maxrss"]
    peak_mb = peak_raw / (1024.0 * 1024.0) if platform.system() == "Darwin" else peak_raw / 1024.0
    return _p95(payload["timings_ms"]), peak_mb


def _p95(values: list[float]) -> float:
    return statistics.quantiles(values, n=100, method="inclusive")[94]


def main() -> None:
    if sys.version_info[:2] != (3, 11):
        raise RuntimeError(f"this must run under Python 3.11, got {sys.version}")

    print("collecting 100-seed cross-process replay artifacts...", file=sys.stderr)
    replay_artifacts = _collect_replay_artifacts()

    print("collecting structured evidence-class records...", file=sys.stderr)
    evidence_records = _collect_evidence_records()

    print("measuring single-episode latency...", file=sys.stderr)
    single_episode_p95_ms = _measure_single_episode_p95_ms()

    print("measuring batch-episode latency and peak memory...", file=sys.stderr)
    batch_episode_p95_ms, peak_memory_mb = _measure_batch_episode_p95_ms_and_peak_memory()

    trace_bytes_p95 = _p95(
        [float(len(str(record["terminal_state"]).encode("utf-8"))) for record in replay_artifacts]
    )

    evidence = {
        "python311_installation": True,
        "license_reviewed": True,
        "replay_artifacts": replay_artifacts,
        "evidence_records": evidence_records,
        "single_episode_p95_ms": single_episode_p95_ms,
        "batch_episode_p95_ms": batch_episode_p95_ms,
        "peak_memory_mb": peak_memory_mb,
        "trace_bytes_p95": int(trace_bytes_p95),
    }

    output_path = _ROOT / "docs" / "release-gates" / "textworld-release-evidence.json"
    output_path.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
