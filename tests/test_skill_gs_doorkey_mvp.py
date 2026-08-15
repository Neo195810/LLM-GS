import tempfile
import unittest
from pathlib import Path

from prog_policies.karel_tasks import DoorKey

from prog_policies.skill_gs.doorkey_state import extract_doorkey_state
from prog_policies.skill_gs.doorkey_policy import DoorKeyFixedPolicy
from prog_policies.skill_gs.evaluator import run_doorkey_mvp, run_many_doorkey_mvp
from prog_policies.skill_gs.skill_manager import JsonSkillStore
from prog_policies.skill_gs.skill_memory import record_skills_from_evaluation


class SkillGSDoorKeyMVPTests(unittest.TestCase):
    def make_task(self, seed=0):
        return DoorKey(
            {
                "env_height": 8,
                "env_width": 8,
                "crashable": False,
                "leaps_behaviour": True,
                "max_calls": 10000,
            },
            seed,
        )

    def test_extracts_key_goal_and_agent_from_seed_zero(self):
        task = self.make_task(seed=0)
        snapshot = extract_doorkey_state(task.get_environment())

        self.assertEqual(snapshot.agent, tuple(task.get_environment().get_hero_pos()))
        self.assertEqual(snapshot.key_cell, task.key_cell)
        self.assertEqual(snapshot.goal_cell, task.end_marker_cell)
        self.assertFalse(snapshot.door_open)

    def test_fixed_policy_solves_seed_zero(self):
        result = run_doorkey_mvp(seed=0)

        self.assertTrue(result["success"])
        self.assertEqual(result["reward"], 1.0)
        self.assertGreater(result["steps"], 0)
        self.assertIn("pickMarker", [step["action"] for step in result["trace"]])
        self.assertIn("putMarker", [step["action"] for step in result["trace"]])
        self.assertEqual(result["plan"]["task"], "DoorKey")
        self.assertTrue(result["critique"]["success"])
        self.assertEqual(result["critique"]["repair_operator"], "store_skill")
        self.assertEqual(result["critique"]["evidence"]["task"], "DoorKey")

    def test_step_budget_failure_gets_repair_critique(self):
        result = run_doorkey_mvp(seed=0, max_steps=1)

        self.assertFalse(result["success"])
        self.assertFalse(result["terminated"])
        self.assertFalse(result["crashed"])
        self.assertFalse(result["critique"]["success"])
        self.assertEqual(result["critique"]["failure_type"], "no_progress")
        self.assertEqual(
            result["critique"]["repair_operator"],
            "retrieve_alternative_skill",
        )

    def test_skill_plan_uses_navigation_for_navigation_subgoals(self):
        result = run_doorkey_mvp(seed=0)
        steps = {
            step["subgoal"]: step["skill_name"]
            for step in result["plan"]["steps"]
        }

        self.assertEqual(steps["locate_key"], "navigate_forward_until_blocked")
        self.assertEqual(steps["navigate_to_key"], "navigate_forward_until_blocked")
        self.assertEqual(steps["navigate_to_door"], "navigate_forward_until_blocked")
        self.assertEqual(steps["navigate_to_goal"], "navigate_forward_until_blocked")
        self.assertEqual(steps["pickup_key"], "pick_marker")
        self.assertEqual(steps["open_door"], "unlock_door_with_key")

    def test_fixed_policy_solves_small_seed_set(self):
        result = run_many_doorkey_mvp(seeds=range(8))

        self.assertEqual(result["success_rate"], 1.0)
        self.assertEqual(result["num_runs"], 8)
        self.assertEqual(result["failed_seeds"], [])
        self.assertEqual(result["critic_decisions"], {"store_skill": 8})

    def test_successful_evaluation_records_skills_to_json_store(self):
        result = run_doorkey_mvp(seed=0)

        with tempfile.TemporaryDirectory() as directory:
            store_path = Path(directory) / "doorkey_skills.json"
            summary = record_skills_from_evaluation(result, store_path)
            record_skills_from_evaluation(run_doorkey_mvp(seed=1), store_path)
            records = JsonSkillStore(store_path).load().all()

        self.assertEqual(summary["stored_skills"], 6)
        self.assertEqual(len(records), 6)
        pickup = next(record for record in records if record.metadata["source_subgoal"] == "pickup_key")
        self.assertEqual(pickup.name, "pick_marker")
        self.assertEqual(pickup.metadata["source_agent"], "critic")
        self.assertEqual(pickup.metadata["created_from"], "successful_run")
        self.assertEqual(pickup.metadata["source_seeds"], [0, 1])
        self.assertEqual(pickup.num_evaluations, 2)

    def test_multi_seed_evaluator_can_persist_cumulative_skill_store(self):
        with tempfile.TemporaryDirectory() as directory:
            store_path = Path(directory) / "doorkey_skills.json"
            result = run_many_doorkey_mvp(seeds=[0, 1], skill_store_path=store_path)
            records = JsonSkillStore(store_path).load().all()

        self.assertEqual(result["successes"], 2)
        self.assertEqual(result["skill_memory"]["stored_skills"], 6)
        self.assertEqual(result["skill_memory"]["updated_skills"], 6)
        self.assertEqual(len(records), 6)
        self.assertTrue(all(record.num_evaluations == 2 for record in records))

    def test_repeated_seed_does_not_duplicate_skill_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            store_path = Path(directory) / "doorkey_skills.json"
            run_many_doorkey_mvp(seeds=[0], skill_store_path=store_path)
            result = run_many_doorkey_mvp(seeds=[0], skill_store_path=store_path)
            records = JsonSkillStore(store_path).load().all()

        self.assertEqual(result["skill_memory"]["stored_skills"], 0)
        self.assertEqual(result["skill_memory"]["updated_skills"], 0)
        self.assertEqual(result["skill_memory"]["skipped_skills"], 6)
        self.assertEqual(len(records), 6)
        self.assertTrue(all(record.num_evaluations == 1 for record in records))

    def test_failed_evaluation_does_not_record_skills(self):
        result = run_doorkey_mvp(seed=0, max_steps=1)

        with tempfile.TemporaryDirectory() as directory:
            store_path = Path(directory) / "doorkey_skills.json"
            summary = record_skills_from_evaluation(result, store_path)
            records = JsonSkillStore(store_path).load().all()

        self.assertEqual(summary["stored_skills"], 0)
        self.assertEqual(summary["skipped_reason"], "critique_not_store_skill")
        self.assertEqual(records, [])

    def test_policy_returns_safe_action_names(self):
        task = self.make_task(seed=0)
        policy = DoorKeyFixedPolicy.from_environment(task.get_environment())

        for _ in range(12):
            action = policy.next_action(task.get_environment())
            self.assertIn(
                action,
                {"move", "turnLeft", "turnRight", "pickMarker", "putMarker"},
            )
            task.get_environment().run_action(action)
            task.get_reward(task.get_environment())


if __name__ == "__main__":
    unittest.main()
