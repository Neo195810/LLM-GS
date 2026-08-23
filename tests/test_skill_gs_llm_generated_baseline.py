import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

from prog_policies.skill_gs.llm_generated_baseline import (
    build_ollama_generate_payload,
    build_openai_responses_payload,
    build_skills_context,
    build_state_conditioned_prompt,
    extract_openai_response_text,
    extract_initial_doorkey_environment_status,
    parse_policy_response,
    run_llm_generated_one_shot_smoke,
)


class SkillGSLLMGeneratedBaselineTests(unittest.TestCase):
    def test_extract_initial_environment_status_includes_prompt_ready_seed_zero_state(self):
        status = extract_initial_doorkey_environment_status(seed=0)

        self.assertEqual(status["seed"], 0)
        self.assertEqual(status["grid_size"], [8, 8])
        self.assertEqual(status["agent"]["position"], [4, 2])
        self.assertEqual(status["agent"]["direction"], "east")
        self.assertEqual(status["key_position"], [5, 2])
        self.assertEqual(status["goal_position"], [1, 6])
        self.assertEqual(status["door_cells"], [[2, 4], [3, 4]])
        self.assertIn("A>", status["ascii_map"])
        self.assertIn("K", status["ascii_map"])
        self.assertIn("G", status["ascii_map"])

    def test_build_state_conditioned_prompt_replaces_environment_state_placeholder(self):
        prompt = build_state_conditioned_prompt(
            template="Rules\n{{environment_state}}\nReturn JSON.",
            environment_status={
                "task": "DoorKey",
                "seed": 0,
                "grid_size": [8, 8],
                "coordinate_system": "zero_indexed_row_col",
                "agent": {"position": [4, 2], "direction": "east"},
                "key_position": [5, 2],
                "goal_position": [1, 6],
                "door_cells": [[2, 4], [3, 4]],
                "wall_column": 4,
                "door_open": False,
                "wall_cells": [[0, 0]],
                "ascii_map": "########\n#.A>#..#\n########",
            },
        )

        self.assertIn("Current Environment State:", prompt)
        self.assertIn("seed: 0", prompt)
        self.assertIn("agent_position: [4, 2]", prompt)
        self.assertIn("agent_direction: east", prompt)
        self.assertIn("door_cells: [[2, 4], [3, 4]]", prompt)
        self.assertIn("ascii_map:", prompt)
        self.assertNotIn("{{environment_state}}", prompt)

    def test_build_state_conditioned_prompt_replaces_skills_context_placeholder(self):
        prompt = build_state_conditioned_prompt(
            template="Rules\n{{environment_state}}\nAvailable Skills:\n{{skills_context}}\nReturn JSON.",
            environment_status={
                "task": "DoorKey",
                "seed": 0,
                "grid_size": [8, 8],
                "coordinate_system": "zero_indexed_row_col",
                "agent": {"position": [4, 2], "direction": "east"},
                "key_position": [5, 2],
                "goal_position": [1, 6],
                "door_cells": [[2, 4], [3, 4]],
                "wall_column": 4,
                "door_open": False,
                "wall_cells": [[0, 0]],
                "ascii_map": "########\n#.A>#..#\n########",
            },
            skills_context=(
                "Skill ID: llm_repair.karel.doorkey.navigate_to_goal_after_key.v1\n"
                "Use when: key_picked and door_open"
            ),
        )

        self.assertIn("Skill ID: llm_repair.karel.doorkey.navigate_to_goal_after_key.v1", prompt)
        self.assertIn("Use when: key_picked and door_open", prompt)
        self.assertNotIn("{{skills_context}}", prompt)

    def test_build_skills_context_formats_repair_skill_store_for_prompt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_store_path = pathlib.Path(temp_dir) / "skills.json"
            _write_repair_skill_store(skill_store_path)

            skills_context = build_skills_context(skill_store_path)

        self.assertIn("Skill ID: llm_repair.karel.doorkey.navigate_to_goal_after_key.v1", skills_context)
        self.assertIn("Name: repair_post_key_navigation_to_goal", skills_context)
        self.assertIn("Preconditions: door_open, key_picked", skills_context)
        self.assertIn("Postconditions: goal_topped_off, success", skills_context)
        self.assertIn("Action Pattern: turnLeft turnLeft move move putMarker", skills_context)

    def test_build_skills_context_reports_no_skills_without_store(self):
        self.assertEqual(
            build_skills_context(None),
            "No learned skills are available yet.",
        )

    def test_build_ollama_payload_can_force_cpu_and_disable_thinking(self):
        payload = build_ollama_generate_payload(
            prompt="Return valid JSON only.",
            model_name="qwen3.5:latest",
            temperature=0.0,
            num_gpu=0,
            num_predict=128,
            think=False,
        )

        self.assertEqual(payload["model"], "qwen3.5:latest")
        self.assertEqual(payload["format"], "json")
        self.assertIs(payload["think"], False)
        self.assertEqual(payload["options"]["temperature"], 0.0)
        self.assertEqual(payload["options"]["num_gpu"], 0)
        self.assertEqual(payload["options"]["num_predict"], 128)

    def test_build_openai_payload_requests_strict_action_sequence_schema(self):
        payload = build_openai_responses_payload(
            prompt="Return valid JSON only.",
            model_name="gpt-5.6-luna",
            temperature=0.0,
            reasoning_effort="none",
            max_output_tokens=512,
        )

        self.assertEqual(payload["model"], "gpt-5.6-luna")
        self.assertEqual(payload["input"], "Return valid JSON only.")
        self.assertEqual(payload["temperature"], 0.0)
        self.assertEqual(payload["reasoning"]["effort"], "none")
        self.assertEqual(payload["max_output_tokens"], 512)
        schema_format = payload["text"]["format"]
        self.assertEqual(schema_format["type"], "json_schema")
        self.assertTrue(schema_format["strict"])
        self.assertEqual(schema_format["schema"]["required"], ["policy_name", "policy_type", "actions", "notes"])
        self.assertEqual(
            schema_format["schema"]["properties"]["actions"]["items"]["enum"],
            ["move", "turnLeft", "turnRight", "pickMarker", "putMarker"],
        )

    def test_extract_openai_response_text_reads_responses_message_content(self):
        response_text = extract_openai_response_text(
            {
                "id": "resp_test",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"policy_name":"p","policy_type":"action_sequence","actions":[],"notes":""}',
                            }
                        ],
                    }
                ],
            }
        )

        self.assertEqual(
            response_text,
            '{"policy_name":"p","policy_type":"action_sequence","actions":[],"notes":""}',
        )

    def test_parse_policy_response_accepts_valid_action_sequence(self):
        policy = parse_policy_response(
            json.dumps(
                {
                    "policy_name": "doorkey_one_shot_policy_v1",
                    "policy_type": "action_sequence",
                    "actions": ["move", "turnLeft", "pickMarker"],
                    "notes": "",
                }
            )
        )

        self.assertEqual(policy["policy_name"], "doorkey_one_shot_policy_v1")
        self.assertEqual(policy["policy_type"], "action_sequence")
        self.assertEqual(policy["actions"], ["move", "turnLeft", "pickMarker"])

    def test_parse_policy_response_rejects_unknown_actions(self):
        with self.assertRaises(ValueError):
            parse_policy_response(
                json.dumps(
                    {
                        "policy_name": "doorkey_one_shot_policy_v1",
                        "policy_type": "action_sequence",
                        "actions": ["move", "teleport"],
                        "notes": "",
                    }
                )
            )

    def test_one_shot_smoke_caches_response_and_evaluates_seed_zero(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            prompt_path = temp_path / "doorkey_one_shot_policy_v1.txt"
            cache_dir = temp_path / "cache"
            prompt_path.write_text(
                "Return valid JSON only.\n{{environment_state}}",
                encoding="utf-8",
            )

            result = run_llm_generated_one_shot_smoke(
                prompt_template_path=prompt_path,
                model_name="fake-model",
                seed=0,
                cache_dir=cache_dir,
                generate_response=_fake_ollama_response,
            )

            self.assertEqual(result["provider"], "Ollama")
            self.assertEqual(result["model_name"], "fake-model")
            self.assertEqual(result["seed"], 0)
            self.assertEqual(result["environment_status"]["agent"]["direction"], "east")
            self.assertIn("Current Environment State:", result["final_prompt"])
            self.assertEqual(result["policy"]["actions"], ["move"])
            self.assertFalse(result["evaluation"]["success"])
            self.assertTrue(pathlib.Path(result["cache_path"]).exists())
            self.assertTrue(pathlib.Path(result["state_cache_path"]).exists())
            self.assertTrue(pathlib.Path(result["prompt_cache_path"]).exists())

    def test_one_shot_smoke_injects_skill_store_context_into_final_prompt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            prompt_path = temp_path / "doorkey_one_shot_policy_v1.txt"
            skill_store_path = temp_path / "skills.json"
            cache_dir = temp_path / "cache"
            prompt_path.write_text(
                "Rules\n{{environment_state}}\nAvailable Skills:\n{{skills_context}}\nReturn JSON.",
                encoding="utf-8",
            )
            _write_repair_skill_store(skill_store_path)

            result = run_llm_generated_one_shot_smoke(
                prompt_template_path=prompt_path,
                model_name="fake-model",
                seed=0,
                cache_dir=cache_dir,
                skill_store_path=skill_store_path,
                generate_response=_fake_ollama_response,
            )

            self.assertEqual(result["skill_store_path"], str(skill_store_path))
            self.assertIn(
                "Skill ID: llm_repair.karel.doorkey.navigate_to_goal_after_key.v1",
                result["final_prompt"],
            )
            self.assertIn("Preconditions: door_open, key_picked", result["final_prompt"])
            self.assertNotIn("{{skills_context}}", result["final_prompt"])

    def test_one_shot_smoke_script_writes_result_with_raw_response_file(self):
        repo_root = pathlib.Path(__file__).resolve().parents[1]
        script_path = repo_root / "scripts" / "skill_gs" / "run_llm_generated_smoke.py"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            prompt_path = temp_path / "prompt.txt"
            raw_response_path = temp_path / "response.json"
            output_path = temp_path / "result.json"
            cache_dir = temp_path / "cache"
            skill_store_path = temp_path / "skills.json"
            prompt_path.write_text(
                "Return valid JSON only.\n{{skills_context}}",
                encoding="utf-8",
            )
            raw_response_path.write_text(_fake_ollama_response("", "", 0.0), encoding="utf-8")
            _write_repair_skill_store(skill_store_path)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--provider",
                    "OpenAI",
                    "--prompt-template",
                    str(prompt_path),
                    "--model",
                    "gpt-5.6-luna",
                    "--seed",
                    "0",
                    "--reasoning-effort",
                    "none",
                    "--max-output-tokens",
                    "512",
                    "--cache-dir",
                    str(cache_dir),
                    "--raw-response-file",
                    str(raw_response_path),
                    "--output",
                    str(output_path),
                    "--skill-store",
                    str(skill_store_path),
                ],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["provider"], "OpenAI")
            self.assertEqual(payload["model_name"], "gpt-5.6-luna")
            self.assertEqual(payload["reasoning_effort"], "none")
            self.assertEqual(payload["max_output_tokens"], 512)
            self.assertEqual(payload["policy"]["actions"], ["move"])
            self.assertEqual(payload["seed"], 0)
            self.assertIn(
                "Skill ID: llm_repair.karel.doorkey.navigate_to_goal_after_key.v1",
                payload["final_prompt"],
            )


def _fake_ollama_response(prompt, model_name, temperature):
    return json.dumps(
        {
            "policy_name": "doorkey_one_shot_policy_v1",
            "policy_type": "action_sequence",
            "actions": ["move"],
            "notes": "minimal fixture",
        }
    )


def _write_repair_skill_store(path):
    path.write_text(
        json.dumps(
            {
                "skills": [
                    {
                        "skill_id": "llm_repair.karel.doorkey.navigate_to_goal_after_key.v1",
                        "name": "repair_post_key_navigation_to_goal",
                        "description": "Navigate from a post-key state to the goal and putMarker.",
                        "task_family": "Karel",
                        "dsl_source": "turnLeft turnLeft move move putMarker",
                        "ast_json": {
                            "type": "action_sequence",
                            "actions": ["turnLeft", "turnLeft", "move", "move", "putMarker"],
                        },
                        "root_nonterminal": "ActionSequence",
                        "semantic_tags": [
                            "doorkey",
                            "goal",
                            "llm_repair",
                            "navigation",
                            "post_key_navigation",
                        ],
                        "preconditions": ["door_open", "key_picked"],
                        "postconditions": ["goal_topped_off", "success"],
                        "success_rate": 1.0,
                        "mean_reward": 1.0,
                        "num_evaluations": 1,
                        "failure_signatures": ["wrong_put_marker_position"],
                        "metadata": {},
                        "version": 1,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
