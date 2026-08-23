import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from prog_policies.skill_gs.llm_generated_baseline import (
    evaluate_doorkey_action_sequence,
)
from prog_policies.skill_gs.llm_repair import repair_doorkey_llm_policy
from prog_policies.skill_gs.skill_manager import JsonSkillStore


LUNA_PROMPT_V4_SEED0_ACTIONS = [
    "turnRight",
    "move",
    "pickMarker",
    "turnLeft",
    "turnLeft",
    "move",
    "move",
    "move",
    "turnLeft",
    "move",
    "move",
    "move",
    "turnRight",
    "move",
    "move",
    "putMarker",
]

LUNA_SKILL_AUGMENTED_SEED1_FAILED_ACTIONS = [
    "turnRight",
    "turnRight",
    "move",
    "move",
    "move",
    "move",
    "turnLeft",
    "move",
    "move",
    "move",
    "turnLeft",
    "move",
    "pickMarker",
    "turnLeft",
    "turnLeft",
    "move",
    "move",
    "turnRight",
    "move",
    "move",
    "move",
    "move",
    "turnLeft",
    "move",
    "move",
    "putMarker",
]


class SkillGSLLMRepairTests(unittest.TestCase):
    def test_repair_splices_post_key_navigation_and_stores_repair_skill(self):
        original_evaluation = evaluate_doorkey_action_sequence(
            seed=0,
            actions=LUNA_PROMPT_V4_SEED0_ACTIONS,
        )
        self.assertFalse(original_evaluation["success"])

        with tempfile.TemporaryDirectory() as directory:
            skill_store_path = Path(directory) / "llm_repair_skills.json"
            result = repair_doorkey_llm_policy(
                {
                    "task": "DoorKey",
                    "seed": 0,
                    "provider": "OpenAI",
                    "model_name": "gpt-5.6-luna",
                    "policy": {
                        "policy_name": "doorkey_one_shot_policy_v1.txt",
                        "policy_type": "action_sequence",
                        "actions": LUNA_PROMPT_V4_SEED0_ACTIONS,
                        "notes": "fixture",
                    },
                    "evaluation": original_evaluation,
                },
                skill_store_path=skill_store_path,
                source_label="prompt_v4",
            )
            records = JsonSkillStore(skill_store_path).load().all()

        self.assertEqual(result["repair_agent"], "LLMRepairAgent")
        self.assertEqual(result["repair_plan"]["strategy_id"], "splice_post_key_navigation")
        self.assertEqual(result["repair_plan"]["preserved_prefix_steps"], 3)
        self.assertEqual(result["repair_plan"]["target_subgoal"], "navigate_to_goal_after_key")
        self.assertTrue(result["repaired_evaluation"]["success"])
        self.assertEqual(result["repaired_evaluation"]["reward"], 1.0)
        self.assertEqual(result["repaired_policy"]["actions"][:3], LUNA_PROMPT_V4_SEED0_ACTIONS[:3])
        self.assertEqual(result["repaired_policy"]["actions"][-1], "putMarker")
        self.assertEqual(result["skill_memory"]["stored_skills"], 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(
            records[0].skill_id,
            "llm_repair.karel.doorkey.navigate_to_goal_after_key.v1",
        )
        self.assertIn("llm_repair", records[0].semantic_tags)
        self.assertIn("post_key_navigation", records[0].semantic_tags)

    def test_repair_replans_before_key_failure_and_stores_key_navigation_skill(self):
        original_evaluation = evaluate_doorkey_action_sequence(
            seed=1,
            actions=LUNA_SKILL_AUGMENTED_SEED1_FAILED_ACTIONS,
        )
        self.assertFalse(original_evaluation["success"])

        with tempfile.TemporaryDirectory() as directory:
            skill_store_path = Path(directory) / "llm_repair_skills.json"
            result = repair_doorkey_llm_policy(
                {
                    "task": "DoorKey",
                    "seed": 1,
                    "provider": "OpenAI",
                    "model_name": "gpt-5.6-luna",
                    "policy": {
                        "policy_name": "doorkey_one_shot_policy_v1.txt",
                        "policy_type": "action_sequence",
                        "actions": LUNA_SKILL_AUGMENTED_SEED1_FAILED_ACTIONS,
                        "notes": "fixture",
                    },
                    "evaluation": original_evaluation,
                },
                skill_store_path=skill_store_path,
                source_label="skill_augmented_seed0_7",
            )
            records = JsonSkillStore(skill_store_path).load().all()

        skill_ids = {record.skill_id for record in records}
        key_skill = next(
            record
            for record in records
            if record.skill_id
            == "llm_repair.karel.doorkey.navigate_to_key_before_door_open.v1"
        )

        self.assertEqual(result["repair_plan"]["strategy_id"], "replan_via_key_then_goal")
        self.assertEqual(result["repair_plan"]["target_subgoal"], "navigate_to_key_before_door_open")
        self.assertTrue(result["repaired_evaluation"]["success"])
        self.assertEqual(result["repaired_evaluation"]["reward"], 1.0)
        self.assertIn(
            "llm_repair.karel.doorkey.navigate_to_key_before_door_open.v1",
            skill_ids,
        )
        self.assertIn(
            "llm_repair.karel.doorkey.navigate_to_goal_after_key.v1",
            skill_ids,
        )
        self.assertIn("key_navigation", key_skill.semantic_tags)
        self.assertEqual(key_skill.dsl_source, "navigate_to key_position then pickMarker")
        self.assertIn(1, key_skill.metadata["source_seeds"])
        self.assertTrue(key_skill.metadata["observed_key_actions"])

    def test_repair_script_reads_result_and_writes_repaired_output(self):
        repo_root = Path(__file__).resolve().parents[1]
        script_path = repo_root / "scripts" / "skill_gs" / "repair_llm_generated_policy.py"
        original_evaluation = evaluate_doorkey_action_sequence(
            seed=0,
            actions=LUNA_PROMPT_V4_SEED0_ACTIONS,
        )

        with tempfile.TemporaryDirectory() as directory:
            temp_path = Path(directory)
            input_path = temp_path / "llm_result.json"
            output_path = temp_path / "repair_result.json"
            skill_store_path = temp_path / "repair_skills.json"
            input_path.write_text(
                json.dumps(
                    {
                        "task": "DoorKey",
                        "seed": 0,
                        "provider": "OpenAI",
                        "model_name": "gpt-5.6-luna",
                        "policy": {
                            "policy_name": "doorkey_one_shot_policy_v1.txt",
                            "policy_type": "action_sequence",
                            "actions": LUNA_PROMPT_V4_SEED0_ACTIONS,
                            "notes": "fixture",
                        },
                        "evaluation": original_evaluation,
                    }
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                    "--skill-store",
                    str(skill_store_path),
                    "--source-label",
                    "prompt_v4",
                ],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["repaired_evaluation"]["success"])
            self.assertTrue(skill_store_path.exists())

    def test_batch_repair_script_repairs_failed_inputs_and_skips_successful_inputs(self):
        repo_root = Path(__file__).resolve().parents[1]
        script_path = repo_root / "scripts" / "skill_gs" / "repair_llm_generated_batch.py"
        failed_evaluation = evaluate_doorkey_action_sequence(
            seed=1,
            actions=LUNA_SKILL_AUGMENTED_SEED1_FAILED_ACTIONS,
        )
        successful_evaluation = evaluate_doorkey_action_sequence(
            seed=0,
            actions=[
                "turnRight",
                "move",
                "pickMarker",
                "turnLeft",
                "turnLeft",
                "move",
                "move",
                "turnRight",
                "move",
                "move",
                "move",
                "move",
                "turnLeft",
                "move",
                "move",
                "putMarker",
            ],
        )

        with tempfile.TemporaryDirectory() as directory:
            temp_path = Path(directory)
            input_dir = temp_path / "inputs"
            output_dir = temp_path / "repairs"
            input_dir.mkdir()
            summary_path = temp_path / "summary.json"
            skill_store_path = temp_path / "repair_skills.json"
            (input_dir / "seed0_success.json").write_text(
                json.dumps(
                    {
                        "task": "DoorKey",
                        "seed": 0,
                        "provider": "OpenAI",
                        "model_name": "gpt-5.6-luna",
                        "policy": {
                            "policy_name": "doorkey_one_shot_policy_v1.txt",
                            "policy_type": "action_sequence",
                            "actions": [],
                            "notes": "already solved fixture",
                        },
                        "evaluation": successful_evaluation,
                    }
                ),
                encoding="utf-8",
            )
            (input_dir / "seed1_failed.json").write_text(
                json.dumps(
                    {
                        "task": "DoorKey",
                        "seed": 1,
                        "provider": "OpenAI",
                        "model_name": "gpt-5.6-luna",
                        "policy": {
                            "policy_name": "doorkey_one_shot_policy_v1.txt",
                            "policy_type": "action_sequence",
                            "actions": LUNA_SKILL_AUGMENTED_SEED1_FAILED_ACTIONS,
                            "notes": "failed fixture",
                        },
                        "evaluation": failed_evaluation,
                    }
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--input-glob",
                    str(input_dir / "*.json"),
                    "--output-dir",
                    str(output_dir),
                    "--skill-store",
                    str(skill_store_path),
                    "--summary-output",
                    str(summary_path),
                    "--source-label",
                    "skill_augmented_seed0_7",
                ],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            records = JsonSkillStore(skill_store_path).load().all()

        self.assertEqual(summary["input_count"], 2)
        self.assertEqual(summary["skipped_successful_count"], 1)
        self.assertEqual(summary["repaired_count"], 1)
        self.assertEqual(summary["successful_repairs"], 1)
        self.assertTrue(summary["results"][1]["output_path"])
        self.assertIn(
            "llm_repair.karel.doorkey.navigate_to_key_before_door_open.v1",
            {record.skill_id for record in records},
        )


if __name__ == "__main__":
    unittest.main()
