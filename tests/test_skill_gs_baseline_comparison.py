import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

from prog_policies.skill_gs.baseline_comparison import (
    run_doorkey_baseline_comparison,
)


class SkillGSBaselineComparisonTests(unittest.TestCase):
    def test_comparison_runs_three_named_groups_with_shared_seed_set(self):
        result = run_doorkey_baseline_comparison(
            seeds=[0, 1],
            initial_max_steps=6,
            search_candidate_max_steps=[6, 50],
            ours_retry_budget_schedule=[50],
            ours_max_attempts=2,
            perturbation_seed=123,
        )

        self.assertEqual(result["task"], "DoorKey")
        self.assertEqual(result["fairness"]["seeds"], [0, 1])
        self.assertEqual(
            [group["name"] for group in result["groups"]],
            [
                "llm_generated",
                "llm_gs_style_search",
                "ours_adaptive_skill_gs",
            ],
        )
        self.assertEqual(len(result["comparison_table"]), 3)
        for group in result["groups"]:
            self.assertEqual(group["num_runs"], 2)

    def test_llm_gs_style_search_counts_all_candidate_evaluations(self):
        result = run_doorkey_baseline_comparison(
            seeds=[0],
            initial_max_steps=6,
            search_candidate_max_steps=[6, 50],
            ours_retry_budget_schedule=[50],
            ours_max_attempts=2,
            perturbation_seed=123,
        )

        search_group = _group_by_name(result, "llm_gs_style_search")

        self.assertEqual(search_group["evaluation_count"], 2)
        self.assertEqual(search_group["selected_candidate"]["max_steps"], 50)
        self.assertEqual(len(search_group["candidate_results"]), 2)

    def test_ours_adaptive_group_uses_retry_budget_schedule(self):
        result = run_doorkey_baseline_comparison(
            seeds=[0],
            initial_max_steps=6,
            search_candidate_max_steps=[6, 50],
            ours_retry_budget_schedule=[50],
            ours_max_attempts=2,
            perturbation_seed=123,
        )

        ours_group = _group_by_name(result, "ours_adaptive_skill_gs")

        self.assertEqual(ours_group["adaptive_retry"]["max_attempts"], 2)
        self.assertEqual(ours_group["adaptive_retry"]["retry_budget_schedule"], [50])
        self.assertGreaterEqual(ours_group["evaluation_count"], 2)

    def test_baseline_comparison_script_writes_json_output(self):
        repo_root = pathlib.Path(__file__).resolve().parents[1]
        script_path = repo_root / "scripts" / "skill_gs" / "run_baseline_comparison.py"
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = pathlib.Path(temp_dir) / "comparison.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--seeds",
                    "0",
                    "--initial-max-steps",
                    "6",
                    "--search-candidate-max-steps",
                    "6",
                    "50",
                    "--ours-retry-budget-schedule",
                    "50",
                    "--ours-max-attempts",
                    "2",
                    "--output",
                    str(output_path),
                ],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(
                [row["name"] for row in payload["comparison_table"]],
                [
                    "llm_generated",
                    "llm_gs_style_search",
                    "ours_adaptive_skill_gs",
                ],
            )


def _group_by_name(result, name):
    return next(group for group in result["groups"] if group["name"] == name)


if __name__ == "__main__":
    unittest.main()
