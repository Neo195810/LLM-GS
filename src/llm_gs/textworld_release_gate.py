"""Formal-benchmark release gate for the TextWorld pilot."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

REQUIRED_EVIDENCE_CLASSES = frozenset(
    {"success", "invalid_action", "unsatisfied_precondition", "timeout", "runtime_error"}
)

# Preregistered formal-benchmark acceptance thresholds (recorded 2026-08-15).
# Set at roughly 2x the measured baseline in docs/release-gates/textworld-release-evidence.json
# (single_episode_p95_ms=2460, batch_episode_p95_ms=293, peak_memory_mb=77, trace_bytes_p95=478),
# to catch regressions without flagging normal run-to-run noise.
SINGLE_EPISODE_P95_MS_THRESHOLD = 5000.0
BATCH_EPISODE_P95_MS_THRESHOLD = 1000.0
PEAK_MEMORY_MB_THRESHOLD = 200.0
TRACE_BYTES_P95_THRESHOLD = 2000


@dataclass(frozen=True)
class ReplayArtifact:
    seed: int
    process_id: str
    terminal_state: str
    evidence_sha256: str
    score: float
    action_count: int


@dataclass(frozen=True)
class EvidenceClassRecord:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class TextWorldReleaseEvidence:
    python311_installation: bool
    license_reviewed: bool
    replay_artifacts: tuple[ReplayArtifact, ...]
    evidence_records: tuple[EvidenceClassRecord, ...]
    single_episode_p95_ms: float | None
    batch_episode_p95_ms: float | None
    peak_memory_mb: float | None
    trace_bytes_p95: int | None


@dataclass(frozen=True)
class TextWorldReleaseGate:
    passed: bool
    unmet_requirements: tuple[str, ...]


def evidence_from_dict(payload: object) -> TextWorldReleaseEvidence:
    """Decode the persisted, reviewable release-evidence artifact strictly."""
    if not isinstance(payload, dict):
        raise ValueError("release evidence must be a JSON object")
    try:
        replay_artifacts = tuple(
            ReplayArtifact(
                seed=_int(item, "seed"),
                process_id=_string(item, "process_id"),
                terminal_state=_string(item, "terminal_state"),
                evidence_sha256=_string(item, "evidence_sha256"),
                score=_number(item, "score"),
                action_count=_int(item, "action_count"),
            )
            for item in _array(payload, "replay_artifacts")
        )
        evidence_records = tuple(
            EvidenceClassRecord(
                name=_string(item, "name"),
                status=_string(item, "status"),
                detail=_string(item, "detail"),
            )
            for item in _array(payload, "evidence_records")
        )
        return TextWorldReleaseEvidence(
            python311_installation=_bool(payload, "python311_installation"),
            license_reviewed=_bool(payload, "license_reviewed"),
            replay_artifacts=replay_artifacts,
            evidence_records=evidence_records,
            single_episode_p95_ms=_number(payload, "single_episode_p95_ms"),
            batch_episode_p95_ms=_number(payload, "batch_episode_p95_ms"),
            peak_memory_mb=_number(payload, "peak_memory_mb"),
            trace_bytes_p95=_int(payload, "trace_bytes_p95"),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"invalid TextWorld release evidence: {error}") from error


def _array(payload: dict[str, Any], name: str) -> list[dict[str, Any]]:
    value = payload[name]
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise TypeError(f"{name} must be an array of objects")
    return value


def _string(payload: dict[str, Any], name: str) -> str:
    value = payload[name]
    if not isinstance(value, str) or not value:
        raise TypeError(f"{name} must be a non-empty string")
    return value


def _bool(payload: dict[str, Any], name: str) -> bool:
    value = payload[name]
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a boolean")
    return value


def _number(payload: dict[str, Any], name: str) -> float:
    value = payload[name]
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value < 0
    ):
        raise TypeError(f"{name} must be a non-negative number")
    return float(value)


def _int(payload: dict[str, Any], name: str) -> int:
    value = payload[name]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TypeError(f"{name} must be a non-negative integer")
    return int(value)


def evaluate_release_gate(evidence: TextWorldReleaseEvidence) -> TextWorldReleaseGate:
    """Reject promotion unless every preregistered formal-benchmark gate passes."""
    unmet: list[str] = []
    if not evidence.python311_installation:
        unmet.append("python311_installation")
    if not evidence.license_reviewed:
        unmet.append("license_review")
    if not _has_100_seed_cross_process_replay(evidence.replay_artifacts):
        unmet.append("100_seed_cross_process_replay")
    if not _has_structured_evidence(evidence.evidence_records):
        unmet.append("structured_evidence")
    if not _has_measurements(evidence):
        unmet.append("measured_performance")
    elif not _within_performance_thresholds(evidence):
        unmet.append("performance_threshold")
    return TextWorldReleaseGate(not unmet, tuple(unmet))


def _has_100_seed_cross_process_replay(artifacts: tuple[ReplayArtifact, ...]) -> bool:
    by_seed: dict[int, list[ReplayArtifact]] = {}
    for artifact in artifacts:
        by_seed.setdefault(artifact.seed, []).append(artifact)
    if len(by_seed) != 100:
        return False
    for pair in by_seed.values():
        if len(pair) != 2 or pair[0].process_id == pair[1].process_id:
            return False
        replay_results = {
            (
                artifact.terminal_state,
                artifact.evidence_sha256,
                artifact.score,
                artifact.action_count,
            )
            for artifact in pair
        }
        if len(replay_results) != 1:
            return False
    return True


def _has_structured_evidence(records: tuple[EvidenceClassRecord, ...]) -> bool:
    by_name = {record.name: record for record in records}
    return all(
        name in by_name
        and by_name[name].status in {"observed", "not_applicable"}
        and bool(by_name[name].detail)
        for name in REQUIRED_EVIDENCE_CLASSES
    )


def _within_performance_thresholds(evidence: TextWorldReleaseEvidence) -> bool:
    assert evidence.single_episode_p95_ms is not None
    assert evidence.batch_episode_p95_ms is not None
    assert evidence.peak_memory_mb is not None
    assert evidence.trace_bytes_p95 is not None
    return (
        evidence.single_episode_p95_ms <= SINGLE_EPISODE_P95_MS_THRESHOLD
        and evidence.batch_episode_p95_ms <= BATCH_EPISODE_P95_MS_THRESHOLD
        and evidence.peak_memory_mb <= PEAK_MEMORY_MB_THRESHOLD
        and evidence.trace_bytes_p95 <= TRACE_BYTES_P95_THRESHOLD
    )


def _has_measurements(evidence: TextWorldReleaseEvidence) -> bool:
    measurements = (
        evidence.single_episode_p95_ms,
        evidence.batch_episode_p95_ms,
        evidence.peak_memory_mb,
        evidence.trace_bytes_p95,
    )
    return all(
        measurement is not None
        and not isinstance(measurement, bool)
        and isfinite(measurement)
        and measurement >= 0
        for measurement in measurements
    )
