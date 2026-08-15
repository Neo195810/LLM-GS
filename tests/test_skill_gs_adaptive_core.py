import json
import tempfile
import unittest
from pathlib import Path

from prog_policies.skill_gs import run_doorkey_retry_loop
from prog_policies.skill_gs.adaptive_memory import AdaptiveAttemptMemory
from prog_policies.skill_gs.evaluator import run_doorkey_mvp
from prog_policies.skill_gs.failure_detector import detect_failure
from prog_policies.skill_gs.replanner import replan_after_failure
from prog_policies.skill_gs.stochastic_perturbation import choose_repair_strategy


class SkillGSAdaptiveCoreTests(unittest.TestCase):
    def test_failure_detector_classifies_step_budget_exhaustion(self):
        evaluation = run_doorkey_mvp(seed=0, max_steps=1)

        diagnosis = detect_failure(evaluation, attempt=1, max_steps=1)

        self.assertFalse(diagnosis.success)
        self.assertEqual(diagnosis.failure_type, "step_budget_exhausted")
        self.assertEqual(diagnosis.severity, "recoverable")
        self.assertEqual(diagnosis.failed_stage, "attempt_execution")
        self.assertEqual(diagnosis.recommended_repair, "increase_step_budget")
        self.assertEqual(diagnosis.evidence["source_failure_type"], "no_progress")
        self.assertEqual(diagnosis.evidence["steps"], 1)

    def test_stochastic_perturbation_is_seeded_and_constrained(self):
        diagnosis = detect_failure(run_doorkey_mvp(seed=0, max_steps=1), max_steps=1)

        first = choose_repair_strategy(diagnosis, seed=123, attempt=1)
        second = choose_repair_strategy(diagnosis, seed=123, attempt=1)

        self.assertEqual(first, second)
        self.assertIn(
            first["strategy_id"],
            ["increase_step_budget", "retrieve_alternative_skill"],
        )
        self.assertEqual(first["failure_type"], "step_budget_exhausted")
        self.assertGreaterEqual(first["random_value"], 0.0)
        self.assertLess(first["random_value"], 1.0)

    def test_replanner_turns_diagnosis_into_next_attempt_config(self):
        diagnosis = detect_failure(run_doorkey_mvp(seed=0, max_steps=1), max_steps=1)
        perturbation = {
            "strategy_id": "increase_step_budget",
            "failure_type": "step_budget_exhausted",
            "random_value": 0.0,
        }

        plan = replan_after_failure(
            diagnosis,
            attempt=1,
            current_max_steps=1,
            retry_max_steps=200,
            perturbation=perturbation,
        )

        self.assertEqual(plan.status, "retry")
        self.assertEqual(plan.strategy_id, "increase_step_budget")
        self.assertEqual(plan.next_attempt["max_steps"], 200)
        self.assertEqual(plan.next_attempt["reason"], "step_budget_exhausted")

    def test_retry_loop_records_adaptive_attempt_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            memory_path = Path(directory) / "adaptive_attempts.json"
            result = run_doorkey_retry_loop(
                seeds=[0],
                initial_max_steps=1,
                retry_max_steps=200,
                max_attempts=2,
                attempt_memory_path=memory_path,
                perturbation_seed=123,
            )
            payload = json.loads(memory_path.read_text(encoding="utf-8"))
            memory = AdaptiveAttemptMemory(memory_path).load().summary()

        self.assertEqual(result["success_rate"], 1.0)
        self.assertEqual(result["adaptive_memory"]["num_attempts"], 2)
        self.assertEqual(result["adaptive_memory"]["successful_repairs"], 1)
        self.assertEqual(memory["successful_repairs"], 1)
        self.assertEqual(len(payload["attempts"]), 2)
        self.assertEqual(payload["attempts"][0]["diagnosis"]["failure_type"], "step_budget_exhausted")
        self.assertEqual(payload["attempts"][0]["repair_plan"]["status"], "retry")
        self.assertTrue(payload["attempts"][1]["success"])


if __name__ == "__main__":
    unittest.main()
