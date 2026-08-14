import unittest

from prog_policies.karel_tasks import DoorKey

from prog_policies.skill_gs.doorkey_state import extract_doorkey_state
from prog_policies.skill_gs.doorkey_policy import DoorKeyFixedPolicy
from prog_policies.skill_gs.evaluator import run_doorkey_mvp, run_many_doorkey_mvp


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
