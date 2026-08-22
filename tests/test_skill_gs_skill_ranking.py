import unittest
import tempfile
from pathlib import Path

from prog_policies.skill_gs import run_doorkey_retry_loop
from prog_policies.skill_gs.adaptive_memory import AdaptiveAttemptMemory
from prog_policies.skill_gs.failure_detector import FailureDiagnosis
from prog_policies.skill_gs.schemas import RetrievedSkill, SkillRecord
from prog_policies.skill_gs.skill_ranker import (
    build_default_doorkey_skill_ranking,
    rank_skills_for_failure,
)


class SkillGSAdaptiveRankingTests(unittest.TestCase):
    def test_step_budget_failure_prefers_low_complexity_high_success_skill(self):
        diagnosis = FailureDiagnosis(
            success=False,
            failure_type="step_budget_exhausted",
            severity="recoverable",
            failed_stage="attempt_execution",
            recommended_repair="increase_step_budget",
            evidence={"task": "DoorKey", "seed": 0},
        )
        candidates = [
            RetrievedSkill(
                skill=SkillRecord(
                    skill_id="karel.nav.long.v1",
                    name="long_navigation_macro",
                    description="Long navigation macro.",
                    task_family="Karel",
                    dsl_source="WHILE c( frontIsClear c) w( move turnLeft move turnRight w)",
                    semantic_tags=["navigation"],
                    success_rate=0.72,
                    mean_reward=0.3,
                    num_evaluations=4,
                ),
                score=8.0,
                reasons=["base_rank"],
            ),
            RetrievedSkill(
                skill=SkillRecord(
                    skill_id="karel.nav.safe.v1",
                    name="safe_turn",
                    description="Short safe navigation correction.",
                    task_family="Karel",
                    dsl_source="turnLeft",
                    semantic_tags=["navigation", "safe"],
                    success_rate=0.97,
                    mean_reward=0.2,
                    num_evaluations=8,
                ),
                score=7.0,
                reasons=["base_rank"],
            ),
        ]

        ranking = rank_skills_for_failure(candidates, diagnosis)

        self.assertEqual(
            ranking["ranking_policy"],
            "prefer_low_complexity_high_success",
        )
        self.assertEqual(
            ranking["ranked_skills"][0]["skill_id"],
            "karel.nav.safe.v1",
        )
        self.assertIn("low_complexity_bonus", ranking["ranked_skills"][0]["reasons"])
        self.assertGreater(
            ranking["ranked_skills"][0]["score_after"],
            ranking["ranked_skills"][1]["score_after"],
        )

    def test_successful_repair_feedback_boosts_matching_skill(self):
        diagnosis = FailureDiagnosis(
            success=False,
            failure_type="step_budget_exhausted",
            severity="recoverable",
            failed_stage="attempt_execution",
            recommended_repair="increase_step_budget",
            evidence={"task": "DoorKey", "seed": 0},
        )
        candidates = [
            RetrievedSkill(
                skill=SkillRecord(
                    skill_id="karel.nav.alpha.v1",
                    name="alpha_navigation",
                    description="Baseline navigation.",
                    task_family="Karel",
                    dsl_source="move",
                    semantic_tags=["navigation"],
                    success_rate=0.9,
                    mean_reward=0.5,
                    num_evaluations=5,
                ),
                score=10.0,
                reasons=["base_rank"],
            ),
            RetrievedSkill(
                skill=SkillRecord(
                    skill_id="karel.nav.beta.v1",
                    name="beta_navigation",
                    description="Navigation with successful repair feedback.",
                    task_family="Karel",
                    dsl_source="move",
                    semantic_tags=["navigation"],
                    success_rate=0.9,
                    mean_reward=0.5,
                    num_evaluations=5,
                ),
                score=10.0,
                reasons=["base_rank"],
            ),
        ]
        skill_feedback = {
            "failure_attribution": "budget_cutoff_after_key",
            "by_skill": {
                "karel.nav.beta.v1": {
                    "attempts": 2,
                    "successful_repairs": 2,
                    "failed_repairs": 0,
                    "success_rate": 1.0,
                    "score_delta": 1.5,
                }
            },
        }

        ranking = rank_skills_for_failure(
            candidates,
            diagnosis,
            skill_feedback=skill_feedback,
        )

        self.assertEqual(
            ranking["ranked_skills"][0]["skill_id"],
            "karel.nav.beta.v1",
        )
        self.assertIn(
            "repair_success_feedback_bonus=1.50",
            ranking["ranked_skills"][0]["reasons"],
        )

    def test_failed_repair_feedback_penalizes_matching_skill(self):
        diagnosis = FailureDiagnosis(
            success=False,
            failure_type="step_budget_exhausted",
            severity="recoverable",
            failed_stage="attempt_execution",
            recommended_repair="increase_step_budget",
            evidence={"task": "DoorKey", "seed": 0},
        )
        candidates = [
            RetrievedSkill(
                skill=SkillRecord(
                    skill_id="karel.nav.alpha.v1",
                    name="alpha_navigation",
                    description="Navigation with failed repair feedback.",
                    task_family="Karel",
                    dsl_source="move",
                    semantic_tags=["navigation"],
                    success_rate=0.9,
                    mean_reward=0.5,
                    num_evaluations=5,
                ),
                score=10.0,
                reasons=["base_rank"],
            ),
            RetrievedSkill(
                skill=SkillRecord(
                    skill_id="karel.nav.beta.v1",
                    name="beta_navigation",
                    description="Alternative navigation.",
                    task_family="Karel",
                    dsl_source="move",
                    semantic_tags=["navigation"],
                    success_rate=0.9,
                    mean_reward=0.5,
                    num_evaluations=5,
                ),
                score=10.0,
                reasons=["base_rank"],
            ),
        ]
        skill_feedback = {
            "failure_attribution": "blocked_motion",
            "by_skill": {
                "karel.nav.alpha.v1": {
                    "attempts": 2,
                    "successful_repairs": 0,
                    "failed_repairs": 2,
                    "success_rate": 0.0,
                    "score_delta": -2.0,
                }
            },
        }

        ranking = rank_skills_for_failure(
            candidates,
            diagnosis,
            skill_feedback=skill_feedback,
        )

        self.assertEqual(
            ranking["ranked_skills"][0]["skill_id"],
            "karel.nav.beta.v1",
        )
        self.assertIn(
            "repair_failure_feedback_penalty=-2.00",
            ranking["ranked_skills"][1]["reasons"],
        )

    def test_retry_loop_passes_memory_feedback_to_skill_ranking(self):
        with tempfile.TemporaryDirectory() as directory:
            memory_path = Path(directory) / "adaptive_attempts.json"
            memory = AdaptiveAttemptMemory(memory_path)
            memory.record_repair_outcome(
                seed=99,
                failure_type="step_budget_exhausted",
                failure_attribution="budget_cutoff_before_key",
                strategy_id="increase_step_budget",
                selected_skill_id="karel.doorkey.navigate_forward_until_blocked.v1",
                observed_solve_steps=16,
                from_attempt=1,
                to_attempt=2,
                success=True,
            )
            memory.save()

            result = run_doorkey_retry_loop(
                seeds=[0],
                initial_max_steps=1,
                retry_max_steps=50,
                max_attempts=2,
                attempt_memory_path=memory_path,
                perturbation_seed=123,
            )

        first_attempt = result["attempts"][0]
        ranking = first_attempt["skill_ranking"]
        top_skill = ranking["ranked_skills"][0]
        self.assertEqual(
            ranking["skill_feedback"]["failure_attribution"],
            "budget_cutoff_before_key",
        )
        self.assertEqual(
            top_skill["skill_id"],
            "karel.doorkey.navigate_forward_until_blocked.v1",
        )
        self.assertIn("repair_success_feedback_bonus", " ".join(top_skill["reasons"]))

    def test_retry_loop_attaches_skill_ranking_to_failed_attempt(self):
        result = run_doorkey_retry_loop(
            seeds=[0],
            initial_max_steps=1,
            retry_max_steps=50,
            max_attempts=2,
            perturbation_seed=123,
        )

        failed_attempt = result["attempts"][0]

        self.assertIn("skill_ranker", result["adaptive_core"])
        self.assertEqual(
            failed_attempt["skill_ranking"]["failure_type"],
            "step_budget_exhausted",
        )
        self.assertGreater(len(failed_attempt["skill_ranking"]["ranked_skills"]), 0)
        self.assertEqual(
            failed_attempt["skill_ranking"]["ranking_policy"],
            "prefer_low_complexity_high_success",
        )

    def test_default_doorkey_ranking_prefers_progress_navigation_over_turn_only(self):
        diagnosis = FailureDiagnosis(
            success=False,
            failure_type="step_budget_exhausted",
            severity="recoverable",
            failed_stage="attempt_execution",
            recommended_repair="increase_step_budget",
            evidence={"task": "DoorKey", "seed": 0},
        )

        ranking = build_default_doorkey_skill_ranking(diagnosis)

        self.assertEqual(
            ranking["ranked_skills"][0]["skill_id"],
            "karel.doorkey.navigate_forward_until_blocked.v1",
        )
        self.assertIn(
            "progress_postcondition_bonus",
            ranking["ranked_skills"][0]["reasons"],
        )


if __name__ == "__main__":
    unittest.main()
