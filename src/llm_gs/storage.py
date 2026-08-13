# ruff: noqa: E501

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from llm_gs.contracts import ExperimentManifest, ExperimentReport
from llm_gs.manifest import canonical_json
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
            seeds = manifest.specification["seeds"]
            if not isinstance(seeds, dict) or not isinstance(seeds.get("task"), list):
                raise ValueError("resolved manifest contains invalid task seeds")
            for seed in seeds["task"]:
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
        artifact_hash = self._put_artifact(episode_json.encode("utf-8"))
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO artifacts(artifact_hash) VALUES (?)", (artifact_hash,)
            )
            connection.execute(
                "INSERT INTO program_attempts(execution_id, source) VALUES (?, ?)",
                (work.execution_id, work.candidate_source),
            )
            connection.execute(
                "INSERT INTO episode_evaluations(execution_id, task_seed, episode_json, artifact_hash) VALUES (?, ?, ?, ?)",
                (work.execution_id, work.seed, episode_json, artifact_hash),
            )
            connection.execute(
                "UPDATE work_units SET status = 'completed' WHERE execution_id = ? AND task_seed = ?",
                (work.execution_id, work.seed),
            )
            connection.execute(
                "UPDATE executions SET episode_evaluations = episode_evaluations + 1 WHERE execution_id = ?",
                (work.execution_id,),
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
        """)
        return connection
