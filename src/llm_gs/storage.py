from __future__ import annotations

import sqlite3
from pathlib import Path

from llm_gs.contracts import ExperimentManifest, ExperimentReport
from llm_gs.manifest import canonical_json


class WorkspaceStore:
    def __init__(self, workspace: Path) -> None:
        workspace.mkdir(parents=True, exist_ok=True)
        self._database = workspace / "attempt-store.sqlite3"

    def next_execution_id(self, experiment_id: str) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM executions WHERE experiment_id = ?", (experiment_id,)
            ).fetchone()
        ordinal = int(row[0]) + 1 if row is not None else 1
        return f"exec_{ordinal:06d}"

    def save(self, manifest: ExperimentManifest, report: ExperimentReport) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO experiments(experiment_id, manifest_json) VALUES (?, ?)",
                (report.experiment_id, canonical_json(manifest.model_dump(mode="json"))),
            )
            connection.execute(
                "INSERT INTO executions(experiment_id, execution_id, report_json) VALUES (?, ?, ?)",
                (
                    report.experiment_id,
                    report.execution_id,
                    canonical_json(report.model_dump(mode="json")),
                ),
            )

    def latest_report(self, experiment_id: str) -> ExperimentReport:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT report_json FROM executions
                WHERE experiment_id = ? ORDER BY execution_id DESC LIMIT 1""",
                (experiment_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"report not found for experiment {experiment_id}")
        return ExperimentReport.model_validate_json(row[0])

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS experiments (
                experiment_id TEXT PRIMARY KEY,
                manifest_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS executions (
                experiment_id TEXT NOT NULL,
                execution_id TEXT NOT NULL,
                report_json TEXT NOT NULL,
                PRIMARY KEY (experiment_id, execution_id),
                FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id)
            );
            """
        )
        return connection
