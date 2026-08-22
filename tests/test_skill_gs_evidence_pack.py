import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

from prog_policies.skill_gs.evidence_pack import generate_evidence_pack


class SkillGSEvidencePackTests(unittest.TestCase):
    def test_generate_evidence_pack_writes_charts_and_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            report_path = temp_path / "demo.md"
            assets_dir = temp_path / "assets"

            result = generate_evidence_pack(
                comparison=_sample_comparison(),
                report_path=report_path,
                assets_dir=assets_dir,
            )

            self.assertEqual(result["report_path"], str(report_path))
            self.assertEqual(len(result["charts"]), 3)
            self.assertTrue((assets_dir / "skill_gs_baseline_success_rate.svg").exists())
            self.assertTrue((assets_dir / "skill_gs_evaluation_count.svg").exists())
            self.assertTrue((assets_dir / "skill_gs_adaptive_repair_breakdown.svg").exists())
            report = report_path.read_text(encoding="utf-8")
            self.assertIn("Skill-GS Demo Evidence Pack", report)
            self.assertIn("llm_generated", report)
            self.assertIn("ours_adaptive_skill_gs", report)

    def test_evidence_pack_script_reads_json_and_writes_outputs(self):
        repo_root = pathlib.Path(__file__).resolve().parents[1]
        script_path = repo_root / "scripts" / "skill_gs" / "generate_evidence_pack.py"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            comparison_path = temp_path / "comparison.json"
            report_path = temp_path / "demo.md"
            assets_dir = temp_path / "assets"
            comparison_path.write_text(
                json.dumps(_sample_comparison()),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--baseline-json",
                    str(comparison_path),
                    "--report",
                    str(report_path),
                    "--assets-dir",
                    str(assets_dir),
                ],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(report_path.exists())
            self.assertTrue((assets_dir / "skill_gs_baseline_success_rate.svg").exists())


def _sample_comparison():
    return {
        "task": "DoorKey",
        "fairness": {
            "seeds": [0, 1, 2, 3],
            "max_allowed_execution_budget": 24,
            "external_llm_calls": False,
        },
        "comparison_table": [
            {
                "name": "llm_generated",
                "strategy_family": "one_shot_program",
                "successes": 1,
                "num_runs": 4,
                "success_rate": 0.25,
                "failed_seeds": [1, 2, 3],
                "average_steps_successful": 9.0,
                "evaluation_count": 4,
                "max_execution_budget": 10,
                "repair_enabled": False,
                "memory_enabled": False,
            },
            {
                "name": "llm_gs_style_search",
                "strategy_family": "candidate_search",
                "successes": 4,
                "num_runs": 4,
                "success_rate": 1.0,
                "failed_seeds": [],
                "average_steps_successful": 15.0,
                "evaluation_count": 16,
                "max_execution_budget": 24,
                "repair_enabled": False,
                "memory_enabled": False,
            },
            {
                "name": "ours_adaptive_skill_gs",
                "strategy_family": "adaptive_retry",
                "successes": 4,
                "num_runs": 4,
                "success_rate": 1.0,
                "failed_seeds": [],
                "average_steps_successful": 15.0,
                "evaluation_count": 7,
                "max_execution_budget": 24,
                "repair_enabled": True,
                "memory_enabled": True,
            },
        ],
        "groups": [
            {
                "name": "ours_adaptive_skill_gs",
                "adaptive_memory": {
                    "successful_repairs": 3,
                    "failed_attempts": 3,
                    "successful_attempts": 4,
                },
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
