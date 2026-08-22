from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class AdaptiveAttemptMemory:
    """Small JSON-backed memory for Adaptive Core attempts and repairs."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self._payload: dict[str, Any] = {
            "attempts": [],
            "repair_outcomes": [],
        }

    def load(self) -> "AdaptiveAttemptMemory":
        if self.path and self.path.exists():
            self._payload = json.loads(self.path.read_text(encoding="utf-8"))
            self._payload.setdefault("attempts", [])
            self._payload.setdefault("repair_outcomes", [])
        return self

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._payload, indent=2),
            encoding="utf-8",
        )

    def record_attempt(self, attempt: dict[str, Any]) -> None:
        self._payload["attempts"].append(attempt)

    def record_repair_outcome(
        self,
        seed: int,
        failure_type: str | None,
        failure_attribution: str | None,
        strategy_id: str | None,
        selected_skill_id: str | None,
        observed_solve_steps: int | None,
        from_attempt: int,
        to_attempt: int,
        success: bool,
    ) -> None:
        self._payload["repair_outcomes"].append(
            {
                "seed": seed,
                "failure_type": failure_type,
                "failure_attribution": failure_attribution,
                "strategy_id": strategy_id,
                "selected_skill_id": selected_skill_id,
                "observed_solve_steps": observed_solve_steps,
                "from_attempt": from_attempt,
                "to_attempt": to_attempt,
                "success": success,
            }
        )

    def summary(self) -> dict[str, Any]:
        attempts = list(self._payload["attempts"])
        outcomes = list(self._payload["repair_outcomes"])
        retried_seeds = sorted({item["seed"] for item in outcomes})
        return {
            "store_path": str(self.path) if self.path else None,
            "num_attempts": len(attempts),
            "successful_attempts": sum(1 for item in attempts if item.get("success")),
            "failed_attempts": sum(1 for item in attempts if not item.get("success")),
            "retried_seeds": retried_seeds,
            "num_repair_outcomes": len(outcomes),
            "successful_repairs": sum(1 for item in outcomes if item.get("success")),
        }
