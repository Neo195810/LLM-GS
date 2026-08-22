from __future__ import annotations

from collections import defaultdict
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

    def skill_feedback(
        self,
        failure_attribution: str | None = None,
    ) -> dict[str, Any]:
        """Summarize repair outcomes as skill-level ranking feedback."""

        by_skill: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "attempts": 0,
                "successful_repairs": 0,
                "failed_repairs": 0,
            }
        )
        for outcome in self._payload["repair_outcomes"]:
            if (
                failure_attribution is not None
                and outcome.get("failure_attribution") != failure_attribution
            ):
                continue
            skill_id = outcome.get("selected_skill_id")
            if not skill_id:
                continue
            item = by_skill[skill_id]
            item["attempts"] += 1
            if outcome.get("success"):
                item["successful_repairs"] += 1
            else:
                item["failed_repairs"] += 1

        normalized = {}
        for skill_id, item in by_skill.items():
            attempts = int(item["attempts"])
            successes = int(item["successful_repairs"])
            failures = int(item["failed_repairs"])
            success_rate = successes / attempts if attempts else 0.0
            score_delta = min(successes * 0.75, 3.0) - min(failures * 1.0, 4.0)
            normalized[skill_id] = {
                "attempts": attempts,
                "successful_repairs": successes,
                "failed_repairs": failures,
                "success_rate": round(success_rate, 6),
                "score_delta": round(score_delta, 6),
            }

        return {
            "source": "adaptive_attempt_memory",
            "failure_attribution": failure_attribution,
            "by_skill": normalized,
        }

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
