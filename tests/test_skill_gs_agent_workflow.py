import tempfile
import unittest
from pathlib import Path

from prog_policies.skill_gs import run_doorkey_agent_loop, run_doorkey_retry_loop
from prog_policies.skill_gs.skill_manager import JsonSkillStore


class SkillGSAgentWorkflowTests(unittest.TestCase):
    def test_agent_loop_reports_roles_data_flow_and_skill_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            store_path = Path(directory) / "agent_skills.json"
            result = run_doorkey_agent_loop(seeds=[0, 1], skill_store_path=store_path)
            records = JsonSkillStore(store_path).load().all()

        self.assertEqual(
            result["agent_sequence"],
            [
                "PlannerAgent",
                "SkillManagerAgent",
                "EvaluatorAgent",
                "CriticRepairAgent",
                "SkillMemoryAgent",
            ],
        )
        self.assertEqual(result["run_summary"]["success_rate"], 1.0)
        self.assertEqual(result["run_summary"]["critic_decisions"], {"store_skill": 2})
        self.assertEqual(result["skill_memory"]["stored_skills"], 6)
        self.assertEqual(result["skill_memory"]["updated_skills"], 6)
        self.assertEqual(len(records), 6)

        artifacts = [edge["artifact"] for edge in result["data_flow"]]
        self.assertEqual(
            artifacts,
            [
                "subgoal_template",
                "retrieved_skill_plan",
                "execution_result",
                "critique",
                "learned_skill_records",
            ],
        )

        preferences = {
            agent["name"]: agent["preference"]
            for agent in result["agents"]
        }
        self.assertEqual(
            preferences["PlannerAgent"],
            "prefer reusable subgoals over raw action sequences",
        )
        self.assertEqual(
            preferences["SkillMemoryAgent"],
            "persist only critic-approved successful skills",
        )

    def test_retry_loop_repairs_step_budget_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            store_path = Path(directory) / "retry_skills.json"
            result = run_doorkey_retry_loop(
                seeds=[0],
                initial_max_steps=1,
                retry_max_steps=200,
                max_attempts=2,
                skill_store_path=store_path,
            )
            records = JsonSkillStore(store_path).load().all()

        self.assertEqual(result["success_rate"], 1.0)
        self.assertEqual(result["retried_seeds"], [0])
        self.assertEqual(result["failed_seeds"], [])
        self.assertEqual(result["attempt_critic_decisions"], {
            "retrieve_alternative_skill": 1,
            "store_skill": 1,
        })
        self.assertEqual(result["skill_memory"]["stored_skills"], 6)
        self.assertEqual(len(records), 6)

        attempt_summaries = result["attempts"]
        self.assertEqual(
            [attempt["max_steps"] for attempt in attempt_summaries],
            [1, 200],
        )
        self.assertEqual(
            [attempt["repair_operator"] for attempt in attempt_summaries],
            ["retrieve_alternative_skill", "store_skill"],
        )
        self.assertEqual(
            [attempt["success"] for attempt in attempt_summaries],
            [False, True],
        )


if __name__ == "__main__":
    unittest.main()
