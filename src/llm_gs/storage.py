# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from llm_gs.contracts import (
    EpisodeResult,
    ExperimentManifest,
    ExperimentReport,
    MemoryEntry,
    RepairAttempt,
    RetrievalOutcome,
)
from llm_gs.manifest import canonical_json
from llm_gs.memory import RETRIEVER_VERSION
from llm_gs.proposer import ModelRequestRecord


@dataclass(frozen=True)
class PendingWork:
    execution_id: str
    seed: int
    candidate_source: str
    model_requests: int


class WorkspaceStore:
    def __init__(self, workspace: Path) -> None:
        workspace.mkdir(parents=True, exist_ok=True)
        self._workspace = workspace
        self._database = workspace / "attempt-store.sqlite3"
        self._artifacts = workspace / "artifacts"
        self._artifacts.mkdir(exist_ok=True)
        with self._connect() as connection:
            connection.execute("UPDATE work_units SET status = 'pending' WHERE status = 'running'")

    def next_execution_id(self, experiment_id: str) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM executions WHERE experiment_id = ?", (experiment_id,)
            ).fetchone()
        return f"exec_{(int(row[0]) if row else 0) + 1:06d}"

    def preregister_frozen_manifest(
        self, manifest: ExperimentManifest, experiment_id: str
    ) -> None:
        """Reserve one immutable formal manifest for a task and method arm."""
        arm = canonical_json(
            {
                "failure_strategy": manifest.failure_strategy["name"],
                "search_strategy": manifest.search_strategy["name"],
                "task": manifest.task["name"],
            }
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO frozen_manifest_registrations(arm_json, experiment_id) VALUES (?, ?)",
                (arm, experiment_id),
            )
            row = connection.execute(
                "SELECT experiment_id FROM frozen_manifest_registrations WHERE arm_json = ?",
                (arm,),
            ).fetchone()
            if row is None or str(row[0]) != experiment_id:
                raise ValueError(
                    "a different Frozen Memory manifest is already preregistered for this task and method arm"
                )
            connection.execute(
                "INSERT OR IGNORE INTO experiments(experiment_id, manifest_json) VALUES (?, ?)",
                (experiment_id, canonical_json(manifest.model_dump(mode="json"))),
            )

    def begin_execution_for_experiment(
        self,
        manifest: ExperimentManifest,
        experiment_id: str,
        execution_id: str,
        candidate_source: str,
        model_requests: int,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO experiments(experiment_id, manifest_json) VALUES (?, ?)",
                (experiment_id, canonical_json(manifest.model_dump(mode="json"))),
            )
            connection.execute(
                "INSERT OR IGNORE INTO executions(experiment_id, execution_id, status, candidate_source, model_requests) VALUES (?, ?, 'running', ?, ?)",
                (experiment_id, execution_id, candidate_source, model_requests),
            )
            specification = manifest.specification
            seeds = specification.get("seeds")
            seed_suite = specification.get("seed_suite")
            if isinstance(seeds, dict) and isinstance(seeds.get("task"), list):
                task_seeds = seeds["task"]
            elif isinstance(seed_suite, dict):
                task_seeds = [
                    seed
                    for partition in ("memory_training", "development", "held_out")
                    for seed in seed_suite.get(partition, [])
                ]
            else:
                raise ValueError("resolved manifest contains invalid task seeds")
            for seed in task_seeds:
                connection.execute(
                    "INSERT OR IGNORE INTO work_units(execution_id, task_seed, status) VALUES (?, ?, 'pending')",
                    (execution_id, int(seed)),
                )

    def next_pending_work(self, experiment_id: str) -> PendingWork | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT w.execution_id, w.task_seed, e.candidate_source, e.model_requests
                FROM work_units w JOIN executions e ON e.execution_id = w.execution_id
                WHERE e.experiment_id = ? AND w.status = 'pending' ORDER BY e.execution_id, w.task_seed LIMIT 1""",
                (experiment_id,),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE work_units SET status = 'running' WHERE execution_id = ? AND task_seed = ?",
                (row[0], row[1]),
            )
        return PendingWork(str(row[0]), int(row[1]), str(row[2]), int(row[3]))

    def complete_work(self, work: PendingWork, episode_json: str) -> None:
        with self._connect() as connection:
            self._record_evaluation(
                connection, work.execution_id, work.seed, work.candidate_source, episode_json
            )
            connection.execute(
                "UPDATE work_units SET status = 'completed' WHERE execution_id = ? AND task_seed = ?",
                (work.execution_id, work.seed),
            )

    def record_evaluation(
        self, execution_id: str, seed: int, candidate_source: str, episode_json: str
    ) -> None:
        artifact_hash = self._put_artifact(episode_json.encode("utf-8"))
        with self._connect() as connection:
            self._record_evaluation(
                connection, execution_id, seed, candidate_source, episode_json, artifact_hash
            )

    def _record_evaluation(
        self,
        connection: sqlite3.Connection,
        execution_id: str,
        seed: int,
        candidate_source: str,
        episode_json: str,
        artifact_hash: str | None = None,
    ) -> None:
        artifact_hash = artifact_hash or self._put_artifact(episode_json.encode("utf-8"))
        connection.execute(
            "INSERT OR IGNORE INTO artifacts(artifact_hash) VALUES (?)", (artifact_hash,)
        )
        connection.execute(
            "INSERT INTO program_attempts(execution_id, source) VALUES (?, ?)",
            (execution_id, candidate_source),
        )
        connection.execute(
            "INSERT INTO episode_evaluations(execution_id, task_seed, episode_json, artifact_hash) VALUES (?, ?, ?, ?)",
            (execution_id, seed, episode_json, artifact_hash),
        )
        connection.execute(
            "UPDATE executions SET episode_evaluations = episode_evaluations + 1 WHERE execution_id = ?",
            (execution_id,),
        )

    def save_model_request_records(
        self, execution_id: str, records: list[ModelRequestRecord]
    ) -> None:
        with self._connect() as connection:
            for record in records:
                connection.execute(
                    """INSERT OR IGNORE INTO model_request_records(
                    execution_id, attempt, input_tokens, output_tokens, cached_tokens, finish_reason,
                    warning) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        execution_id,
                        record.attempt,
                        record.input_tokens,
                        record.output_tokens,
                        record.cached_tokens,
                        record.finish_reason,
                        record.warning,
                    ),
                )

    def save_repair_attempt(self, execution_id: str, repair: RepairAttempt) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO repair_attempts(
                execution_id, round, parent_source, candidate_source, diagnosis_json, intent_json,
                normalized_ast_difference) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    execution_id,
                    repair.round,
                    repair.parent_source,
                    repair.candidate.source,
                    repair.diagnosis.model_dump_json(),
                    repair.intent.model_dump_json(),
                    repair.normalized_ast_difference,
                ),
            )

    def save_memory_entry(self, entry: MemoryEntry) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO memory_entries(entry_id, entry_json) VALUES (?, ?)",
                (entry.entry_id, entry.model_dump_json()),
            )

    def memory_entries(self) -> list[MemoryEntry]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT entry_json FROM memory_entries ORDER BY entry_id"
            ).fetchall()
        return [MemoryEntry.model_validate_json(row[0]) for row in rows]

    def freeze_memory_snapshot(
        self, execution_id: str, entries: list[MemoryEntry] | None = None
    ) -> list[MemoryEntry]:
        """Persist the exact read-only memory membership available to one execution."""
        try:
            return self.memory_snapshot_entries(execution_id)
        except ValueError:
            pass
        entries = self.memory_entries() if entries is None else sorted(entries, key=lambda entry: entry.entry_id)
        snapshot_payload = canonical_json(
            {
                "retriever_version": RETRIEVER_VERSION,
                "entries": [entry.model_dump(mode="json") for entry in entries],
            }
        )
        snapshot_id = f"snapshot_{hashlib.sha256(snapshot_payload.encode()).hexdigest()}"
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO memory_snapshots(snapshot_id, snapshot_json) VALUES (?, ?)",
                (snapshot_id, snapshot_payload),
            )
            connection.execute(
                "INSERT OR IGNORE INTO execution_memory_snapshots(execution_id, snapshot_id) VALUES (?, ?)",
                (execution_id, snapshot_id),
            )
        return entries

    def memory_snapshot_entries_by_id(self, snapshot_id: str) -> list[MemoryEntry]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT snapshot_json FROM memory_snapshots WHERE snapshot_id = ?", (snapshot_id,)
            ).fetchone()
        if row is None:
            raise ValueError(f"memory snapshot not found: {snapshot_id}")
        snapshot = json.loads(str(row[0]))
        return [MemoryEntry.model_validate(entry) for entry in snapshot["entries"]]

    def memory_snapshot_id(self, execution_id: str) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT snapshot_id FROM execution_memory_snapshots WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"memory snapshot not found for execution {execution_id}")
        return str(row[0])

    def execution_candidate_source(self, execution_id: str) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT candidate_source FROM executions WHERE execution_id = ?", (execution_id,)
            ).fetchone()
        if row is None:
            raise ValueError(f"execution not found: {execution_id}")
        return str(row[0])

    def memory_snapshot_entries(self, execution_id: str) -> list[MemoryEntry]:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT s.snapshot_json FROM execution_memory_snapshots e
                JOIN memory_snapshots s ON s.snapshot_id = e.snapshot_id
                WHERE e.execution_id = ?""",
                (execution_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"memory snapshot not found for execution {execution_id}")
        snapshot = json.loads(str(row[0]))
        return [MemoryEntry.model_validate(entry) for entry in snapshot["entries"]]

    def fork_memory_lineage(
        self,
        execution_id: str,
        starting_entries: list[MemoryEntry],
        arm_identity: dict[str, str | int],
        parent_snapshot_id: str | None = None,
    ) -> str:
        """Create the deterministic, isolated Online Memory view for one experiment arm."""
        if parent_snapshot_id is None:
            snapshot_entries = self.freeze_memory_snapshot(execution_id, starting_entries)
            snapshot_id = self.memory_snapshot_id(execution_id)
        else:
            snapshot_entries = self.memory_snapshot_entries_by_id(parent_snapshot_id)
            snapshot_id = parent_snapshot_id
            with self._connect() as connection:
                connection.execute(
                    "INSERT OR IGNORE INTO execution_memory_snapshots(execution_id, snapshot_id) VALUES (?, ?)",
                    (execution_id, snapshot_id),
                )
        lineage_payload = canonical_json(
            {
                "arm": arm_identity,
                "execution_id": execution_id,
                "parent_snapshot_id": snapshot_id,
                "protocol": "online-v1",
            }
        )
        lineage_id = f"lineage_{hashlib.sha256(lineage_payload.encode()).hexdigest()}"
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT lineage_id FROM execution_memory_lineages WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != lineage_id:
                    raise ValueError("execution already belongs to a different memory lineage")
                return lineage_id
            connection.execute(
                "INSERT OR IGNORE INTO memory_lineages(lineage_id, parent_snapshot_id, arm_json) VALUES (?, ?, ?)",
                (lineage_id, snapshot_id, canonical_json(arm_identity)),
            )
            connection.execute(
                "INSERT INTO execution_memory_lineages(execution_id, lineage_id) VALUES (?, ?)",
                (execution_id, lineage_id),
            )
            for position, entry in enumerate(snapshot_entries):
                connection.execute(
                    "INSERT OR IGNORE INTO memory_entries(entry_id, entry_json) VALUES (?, ?)",
                    (entry.entry_id, entry.model_dump_json()),
                )
                connection.execute(
                    "INSERT OR IGNORE INTO memory_lineage_entries(lineage_id, entry_id, position) VALUES (?, ?, ?)",
                    (lineage_id, entry.entry_id, position),
                )
        return lineage_id

    def memory_lineage_id(self, execution_id: str) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT lineage_id FROM execution_memory_lineages WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"memory lineage not found for execution {execution_id}")
        return str(row[0])

    def append_memory_lineage_entries(
        self, execution_id: str, entries: list[MemoryEntry]
    ) -> None:
        """Append updates after a decision boundary; no other execution can write this lineage."""
        lineage_id = self.memory_lineage_id(execution_id)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(position), -1) FROM memory_lineage_entries WHERE lineage_id = ?",
                (lineage_id,),
            ).fetchone()
            position = int(row[0]) + 1 if row is not None else 0
            for entry in entries:
                connection.execute(
                    "INSERT OR IGNORE INTO memory_entries(entry_id, entry_json) VALUES (?, ?)",
                    (entry.entry_id, entry.model_dump_json()),
                )
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO memory_lineage_entries(lineage_id, entry_id, position) VALUES (?, ?, ?)",
                    (lineage_id, entry.entry_id, position),
                )
                if cursor.rowcount == 1:
                    position += 1

    def memory_lineage_entries(self, execution_id: str) -> list[MemoryEntry]:
        lineage_id = self.memory_lineage_id(execution_id)
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT e.entry_json FROM memory_lineage_entries l
                JOIN memory_entries e ON e.entry_id = l.entry_id
                WHERE l.lineage_id = ? ORDER BY l.position""",
                (lineage_id,),
            ).fetchall()
        return [MemoryEntry.model_validate_json(row[0]) for row in rows]

    def memory_lineage_audit(self, execution_id: str) -> dict[str, str]:
        lineage_id = self.memory_lineage_id(execution_id)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT parent_snapshot_id FROM memory_lineages WHERE lineage_id = ?", (lineage_id,)
            ).fetchone()
        if row is None:
            raise ValueError(f"memory lineage not found for execution {execution_id}")
        return {
            "lineage_id": lineage_id,
            "parent_snapshot_id": str(row[0]),
            "protocol": "online-v1",
        }

    def save_retrieval_outcome(self, execution_id: str, outcome: RetrievalOutcome) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO retrieval_outcomes(execution_id, outcome_json) VALUES (?, ?)",
                (execution_id, outcome.model_dump_json()),
            )
        if cursor.lastrowid is None:
            raise RuntimeError("retrieval outcome insert did not return an identifier")
        return cursor.lastrowid

    def record_retrieval_impact(
        self,
        retrieval_id: int,
        previous: list[EpisodeResult],
        subsequent: list[EpisodeResult],
    ) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT outcome_json FROM retrieval_outcomes WHERE id = ?", (retrieval_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"retrieval outcome not found: {retrieval_id}")
            outcome = RetrievalOutcome.model_validate_json(row[0])
            updated = outcome.model_copy(
                update={
                    "subsequent_attempted": True,
                    "subsequent_improvement": sum(item.normalized_progress for item in subsequent)
                    > sum(item.normalized_progress for item in previous),
                    "subsequent_failure_type_changed": {
                        item.failure_type for item in subsequent
                    }
                    != {item.failure_type for item in previous},
                    "subsequent_success": any(item.outcome == "success" for item in subsequent),
                }
            )
            connection.execute(
                "UPDATE retrieval_outcomes SET outcome_json = ? WHERE id = ?",
                (updated.model_dump_json(), retrieval_id),
            )

    def record_no_retrieval_impact(self, retrieval_id: int) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT outcome_json FROM retrieval_outcomes WHERE id = ?", (retrieval_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"retrieval outcome not found: {retrieval_id}")
            outcome = RetrievalOutcome.model_validate_json(row[0])
            updated = outcome.model_copy(
                update={
                    "subsequent_attempted": False,
                    "subsequent_improvement": False,
                    "subsequent_failure_type_changed": False,
                    "subsequent_success": False,
                }
            )
            connection.execute(
                "UPDATE retrieval_outcomes SET outcome_json = ? WHERE id = ?",
                (updated.model_dump_json(), retrieval_id),
            )

    def execution_audit(self, execution_id: str) -> dict[str, object]:
        with self._connect() as connection:
            usage = connection.execute(
                "SELECT model_requests, episode_evaluations FROM executions WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
            retrieval_rows = connection.execute(
                "SELECT outcome_json FROM retrieval_outcomes WHERE execution_id = ? ORDER BY id",
                (execution_id,),
            ).fetchall()
            repair_rows = connection.execute(
                """SELECT round, parent_source, candidate_source, normalized_ast_difference
                FROM repair_attempts WHERE execution_id = ? ORDER BY round""",
                (execution_id,),
            ).fetchall()
        if usage is None:
            raise ValueError(f"execution not found: {execution_id}")
        try:
            snapshot_id: str | None = self.memory_snapshot_id(execution_id)
        except ValueError:
            snapshot_id = None
        return {
            "memory_snapshot_id": snapshot_id,
            "retrievals": [json.loads(str(row[0])) for row in retrieval_rows],
            "repairs": [
                {
                    "round": int(row[0]),
                    "parent_source": str(row[1]),
                    "candidate_source": str(row[2]),
                    "normalized_ast_difference": str(row[3]),
                }
                for row in repair_rows
            ],
            "resource_usage": {
                "model_requests": int(usage[0]),
                "episode_evaluations": int(usage[1]),
            },
        }

    def save(self, manifest: ExperimentManifest, report: ExperimentReport) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE executions SET status = 'completed', report_json = ? WHERE execution_id = ?",
                (canonical_json(report.model_dump(mode="json")), report.execution_id),
            )

    def latest_report(self, experiment_id: str) -> ExperimentReport:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT report_json FROM executions WHERE experiment_id = ? AND status = 'completed' ORDER BY execution_id DESC LIMIT 1",
                (experiment_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"report not found for experiment {experiment_id}")
        return ExperimentReport.model_validate_json(row[0])

    def has_completed_execution(self, experiment_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM executions WHERE experiment_id = ? AND status = 'completed' LIMIT 1",
                (experiment_id,),
            ).fetchone()
        return row is not None

    def completed_episode_results(self, execution_id: str) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT episode_json FROM episode_evaluations WHERE execution_id = ? ORDER BY task_seed",
                (execution_id,),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def active_execution_id(self, experiment_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT execution_id FROM executions WHERE experiment_id = ? AND status = 'running' ORDER BY execution_id DESC LIMIT 1",
                (experiment_id,),
            ).fetchone()
        return str(row[0]) if row is not None else None

    def manifest(self, experiment_id: str) -> ExperimentManifest:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT manifest_json FROM experiments WHERE experiment_id = ?", (experiment_id,)
            ).fetchone()
        if row is None:
            raise ValueError(f"experiment not found: {experiment_id}")
        return ExperimentManifest.model_validate_json(row[0])

    def model_requests(self, execution_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT model_requests FROM executions WHERE execution_id = ?", (execution_id,)
            ).fetchone()
        if row is None:
            raise ValueError(f"execution not found: {execution_id}")
        return int(row[0])

    def add_model_requests(self, execution_id: str, count: int) -> None:
        if count < 1:
            raise ValueError("model request count must be positive")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE executions SET model_requests = model_requests + ? WHERE execution_id = ?",
                (count, execution_id),
            )
        if cursor.rowcount != 1:
            raise ValueError(f"execution not found: {execution_id}")

    def _put_artifact(self, content: bytes) -> str:
        digest = hashlib.sha256(content).hexdigest()
        path = self._artifacts / digest
        if not path.exists():
            path.write_bytes(content)
        return f"sha256:{digest}"

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript("""
        CREATE TABLE IF NOT EXISTS experiments (experiment_id TEXT PRIMARY KEY, manifest_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS executions (experiment_id TEXT NOT NULL, execution_id TEXT PRIMARY KEY, status TEXT NOT NULL, candidate_source TEXT NOT NULL, model_requests INTEGER NOT NULL, episode_evaluations INTEGER NOT NULL DEFAULT 0, report_json TEXT);
        CREATE TABLE IF NOT EXISTS work_units (execution_id TEXT NOT NULL, task_seed INTEGER NOT NULL, status TEXT NOT NULL, PRIMARY KEY (execution_id, task_seed));
        CREATE TABLE IF NOT EXISTS program_attempts (id INTEGER PRIMARY KEY, execution_id TEXT NOT NULL, source TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS artifacts (artifact_hash TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS episode_evaluations (id INTEGER PRIMARY KEY, execution_id TEXT NOT NULL, task_seed INTEGER NOT NULL, episode_json TEXT NOT NULL, artifact_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS model_request_records (execution_id TEXT NOT NULL, attempt INTEGER NOT NULL, input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL, cached_tokens INTEGER NOT NULL, finish_reason TEXT, warning TEXT, PRIMARY KEY (execution_id, attempt));
        CREATE TABLE IF NOT EXISTS repair_attempts (id INTEGER PRIMARY KEY, execution_id TEXT NOT NULL, round INTEGER NOT NULL, parent_source TEXT NOT NULL, candidate_source TEXT NOT NULL, diagnosis_json TEXT NOT NULL, intent_json TEXT NOT NULL, normalized_ast_difference TEXT NOT NULL, UNIQUE(execution_id, round));
        CREATE TABLE IF NOT EXISTS memory_entries (entry_id TEXT PRIMARY KEY, entry_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS memory_snapshots (snapshot_id TEXT PRIMARY KEY, snapshot_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS execution_memory_snapshots (execution_id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS memory_lineages (lineage_id TEXT PRIMARY KEY, parent_snapshot_id TEXT NOT NULL, arm_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS execution_memory_lineages (execution_id TEXT PRIMARY KEY, lineage_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS memory_lineage_entries (lineage_id TEXT NOT NULL, entry_id TEXT NOT NULL, position INTEGER NOT NULL, PRIMARY KEY (lineage_id, entry_id), UNIQUE(lineage_id, position));
        CREATE TABLE IF NOT EXISTS frozen_manifest_registrations (arm_json TEXT PRIMARY KEY, experiment_id TEXT NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS retrieval_outcomes (id INTEGER PRIMARY KEY, execution_id TEXT NOT NULL, outcome_json TEXT NOT NULL);
        """)
        return connection
