import json
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from prog_policies.skill_gs.dashboard_data import (
    DashboardDatasetConfig,
    load_dataset_summary,
    load_seed_detail,
    load_skill_rows,
    trace_to_rows,
)


class SkillGSDashboardDataTests(unittest.TestCase):
    def test_load_dataset_summary_combines_one_shot_and_repair_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_demo_dataset(root)
            config = _demo_config()

            summary = load_dataset_summary(root, config)

        self.assertEqual(summary["dataset_id"], "demo")
        self.assertEqual(summary["seeds"], [0, 1])
        self.assertEqual(summary["one_shot_successes"], 1)
        self.assertEqual(summary["one_shot_total"], 2)
        self.assertEqual(summary["repair_successes"], 2)
        self.assertEqual(summary["repair_total"], 2)
        self.assertEqual(summary["failure_stage_counts"], {"after_key_before_goal": 1})
        self.assertEqual(summary["attribution_counts"], {"blocked_motion": 1})
        self.assertEqual(summary["repair_strategy_counts"], {"splice_post_key_navigation": 1})

    def test_load_seed_detail_returns_policy_trace_attribution_and_repair_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_demo_dataset(root)
            config = _demo_config()

            detail = load_seed_detail(root, config, 0)

        self.assertEqual(detail["seed"], 0)
        self.assertEqual(detail["dataset_label"], "Demo Provider")
        self.assertEqual(detail["environment_status"]["agent"]["position"], [4, 2])
        self.assertEqual(detail["policy_actions"], ["move", "pickMarker"])
        self.assertFalse(detail["one_shot_success"])
        self.assertEqual(detail["source_attribution"]["attribution"], "blocked_motion")
        self.assertEqual(detail["repair_plan"]["strategy_id"], "splice_post_key_navigation")
        self.assertTrue(detail["repaired_success"])
        self.assertEqual(detail["repaired_steps"], 5)
        self.assertEqual(len(detail["one_shot_trace_rows"]), 2)
        self.assertEqual(len(detail["repaired_trace_rows"]), 3)

    def test_load_seed_detail_handles_successful_one_shot_without_repair_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_demo_dataset(root)
            config = _demo_config()

            detail = load_seed_detail(root, config, 1)

        self.assertEqual(detail["seed"], 1)
        self.assertTrue(detail["one_shot_success"])
        self.assertIsNone(detail["repair_plan"])
        self.assertIsNone(detail["source_attribution"])
        self.assertTrue(detail["repaired_success"])

    def test_trace_to_rows_formats_agent_positions_for_tables(self):
        rows = trace_to_rows(
            [
                {
                    "step": 1,
                    "action": "move",
                    "agent_before": [4, 2, 1],
                    "agent_after": [4, 3, 1],
                    "instant_reward": 0.0,
                    "total_reward": 0.0,
                    "door_open": False,
                }
            ]
        )

        self.assertEqual(
            rows,
            [
                {
                    "step": 1,
                    "action": "move",
                    "agent_before": "[4, 2, 1]",
                    "agent_after": "[4, 3, 1]",
                    "instant_reward": 0.0,
                    "total_reward": 0.0,
                    "door_open": False,
                }
            ],
        )

    def test_load_skill_rows_summarizes_large_seed_lists(self):
        with tempfile.TemporaryDirectory() as directory:
            skill_store_path = Path(directory) / "skills.json"
            _write_json(
                skill_store_path,
                {
                    "skills": [
                        {
                            "skill_id": "skill.alpha",
                            "name": "Alpha Skill",
                            "task_family": "Karel",
                            "success_rate": 1.0,
                            "num_evaluations": 3000,
                            "failure_signatures": ["blocked_motion", "wrong_put_marker_position"],
                            "metadata": {"source_seeds": list(range(3000))},
                        }
                    ]
                },
            )

            rows = load_skill_rows(skill_store_path)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["skill_id"], "skill.alpha")
        self.assertEqual(rows[0]["num_evaluations"], 3000)
        self.assertEqual(rows[0]["source_seed_count"], 3000)
        self.assertEqual(rows[0]["example_source_seeds"], "0, 1, 2, 3, 4, ...")


class SkillGSDashboardAppTests(unittest.TestCase):
    def test_dashboard_script_bypasses_proxy_for_localhost_on_import(self):
        with mock.patch.dict(os.environ, {"NO_PROXY": "example.com"}, clear=False):
            _load_dashboard_script()

            self.assertIn("example.com", os.environ["NO_PROXY"])
            self.assertIn("localhost", os.environ["NO_PROXY"])
            self.assertIn("127.0.0.1", os.environ["NO_PROXY"])
            self.assertIn("::1", os.environ["NO_PROXY"])
            self.assertEqual(os.environ["GRADIO_ANALYTICS_ENABLED"], "False")

    def test_dashboard_script_help_runs_from_repo_root(self):
        script_path = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "skill_gs"
            / "run_skill_gs_dashboard.py"
        )

        result = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Open the Skill-GS JSON demo dashboard", result.stdout)
        self.assertIn("--share", result.stdout)

    def test_dashboard_app_builds_from_json_results(self):
        if importlib.util.find_spec("gradio") is None:
            self.skipTest("gradio is not installed in this Python environment")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_demo_dataset(root)
            skill_store_path = root / "skills.json"
            _write_json(
                skill_store_path,
                {
                    "skills": [
                        {
                            "skill_id": "skill.alpha",
                            "name": "Alpha Skill",
                            "task_family": "Karel",
                            "success_rate": 1.0,
                            "num_evaluations": 2,
                            "failure_signatures": ["blocked_motion"],
                        }
                    ]
                },
            )

            dashboard = _load_dashboard_script()
            app = dashboard.build_app(
                output_root=root,
                skill_store_path=skill_store_path,
                dataset_configs=(_demo_config(),),
            )

        components = app.get_config_file()["components"]
        labels = {
            component.get("props", {}).get("label")
            for component in components
            if component.get("props", {}).get("label")
        }
        self.assertIn("Overview", labels)
        self.assertIn("Dataset", labels)
        self.assertIn("Seed", labels)
        self.assertIn("One-shot Trace", labels)
        self.assertIn("Repaired Trace", labels)
        self.assertIn("Skill Memory", labels)


def _load_dashboard_script():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "skill_gs" / "run_skill_gs_dashboard.py"
    spec = importlib.util.spec_from_file_location("run_skill_gs_dashboard", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _demo_config():
    return DashboardDatasetConfig(
        dataset_id="demo",
        label="Demo Provider",
        one_shot_globs=("one_shot/seed*_smoke.json",),
        repair_summary_paths=("repair_summary.json",),
    )


def _write_demo_dataset(root):
    one_shot_dir = root / "one_shot"
    one_shot_dir.mkdir()
    repairs_dir = root / "repairs"
    repairs_dir.mkdir()

    _write_json(
        one_shot_dir / "seed0_smoke.json",
        {
            "task": "DoorKey",
            "seed": 0,
            "environment_status": {
                "agent": {"position": [4, 2], "direction": "east"},
                "key_position": [5, 2],
                "goal_position": [1, 6],
                "ascii_map": "########\n#A K G #\n########",
            },
            "policy": {
                "policy_name": "demo",
                "policy_type": "action_sequence",
                "actions": ["move", "pickMarker"],
                "notes": "",
            },
            "evaluation": {
                "success": False,
                "reward": -0.5,
                "steps": 2,
                "trace": [
                    _trace_step(1, "move", [4, 2, 1], [5, 2, 1]),
                    _trace_step(2, "pickMarker", [5, 2, 1], [5, 2, 1], total_reward=0.5),
                ],
            },
        },
    )
    _write_json(
        one_shot_dir / "seed1_smoke.json",
        {
            "task": "DoorKey",
            "seed": 1,
            "environment_status": {
                "agent": {"position": [1, 1], "direction": "south"},
                "key_position": [2, 1],
                "goal_position": [6, 6],
                "ascii_map": "########\n#A.....#\n########",
            },
            "policy": {"actions": ["move", "pickMarker", "putMarker"]},
            "evaluation": {"success": True, "reward": 1.0, "steps": 3, "trace": []},
        },
    )
    _write_json(
        repairs_dir / "seed0_repair.json",
        {
            "task": "DoorKey",
            "seed": 0,
            "source_attribution": {
                "stage_at_end": "after_key_before_goal",
                "attribution": "blocked_motion",
                "blocked_moves": 2,
            },
            "repair_plan": {
                "strategy_id": "splice_post_key_navigation",
                "target_subgoal": "navigate_to_goal_after_key",
                "rationale": "Replace failed suffix.",
            },
            "repaired_evaluation": {
                "success": True,
                "reward": 1.0,
                "steps": 5,
                "trace": [
                    _trace_step(1, "move", [4, 2, 1], [5, 2, 1]),
                    _trace_step(2, "pickMarker", [5, 2, 1], [5, 2, 1], total_reward=0.5),
                    _trace_step(3, "putMarker", [1, 6, 1], [1, 6, 1], total_reward=1.0),
                ],
            },
        },
    )
    _write_json(
        root / "repair_summary.json",
        {
            "source_label": "demo",
            "input_count": 2,
            "results": [
                {
                    "seed": 0,
                    "input_path": "one_shot/seed0_smoke.json",
                    "status": "repaired",
                    "strategy_id": "splice_post_key_navigation",
                    "target_subgoal": "navigate_to_goal_after_key",
                    "output_path": "repairs/seed0_repair.json",
                    "success": True,
                    "steps": 5,
                },
                {
                    "seed": 1,
                    "input_path": "one_shot/seed1_smoke.json",
                    "status": "skipped_successful",
                    "output_path": "",
                    "success": True,
                },
            ],
        },
    )


def _trace_step(
    step,
    action,
    agent_before,
    agent_after,
    instant_reward=0.0,
    total_reward=0.0,
    door_open=False,
):
    return {
        "step": step,
        "action": action,
        "agent_before": agent_before,
        "agent_after": agent_after,
        "instant_reward": instant_reward,
        "total_reward": total_reward,
        "door_open": door_open,
    }


def _write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
