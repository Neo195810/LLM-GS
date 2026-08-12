import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from llm.llm_program_generator import LLMProgramGenerator
from prog_policies.karel import KarelDSL
from prog_policies.search_methods.hill_climbing import HillClimbing
from prog_policies.utils.experiment_events import EventReporter


class _Generation:
    def __init__(self, text):
        self.text = text


class _Response:
    def __init__(self, count):
        self.generations = [[_Generation(f"response-{index}") for index in range(count)]]


class _FakeChatOpenAI:
    calls = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls.append(kwargs)

    def generate(self, messages):
        return _Response(self.kwargs["n"])


class _Task:
    def __init__(self, rewards):
        self.rewards = iter(rewards)
        self.program_num = 0

    def evaluate_program(self, program):
        self.program_num += 1
        return next(self.rewards)


class LocalLLMTests(unittest.TestCase):
    def setUp(self):
        _FakeChatOpenAI.calls = []
        self.dsl = KarelDSL()

    @mock.patch("llm.llm_program_generator.ChatOpenAI", _FakeChatOpenAI)
    def test_ollama_calls_are_batched_without_openai_key(self):
        generator = LLMProgramGenerator(
            0,
            "DoorKey",
            self.dsl,
            2,
            llm_provider="ollama",
            llm_batch_size=2,
        )
        with mock.patch.dict(os.environ, {}, clear=True):
            responses = generator._call_llm("system", "user", 5, 12)

        self.assertEqual(len(responses), 5)
        self.assertEqual([call["n"] for call in _FakeChatOpenAI.calls], [2, 2, 1])
        self.assertTrue(all(call["api_key"] == "ollama" for call in _FakeChatOpenAI.calls))
        self.assertTrue(all(call["base_url"].endswith("/v1") for call in _FakeChatOpenAI.calls))
        self.assertEqual(_FakeChatOpenAI.calls[0]["model_kwargs"]["seed"], 12)
        self.assertTrue(all(call["max_tokens"] == 1024 for call in _FakeChatOpenAI.calls))
        self.assertTrue(all(call["timeout"] == 300 for call in _FakeChatOpenAI.calls))
        self.assertTrue(all(call["max_retries"] == 0 for call in _FakeChatOpenAI.calls))

    @mock.patch("llm.llm_program_generator.ChatOpenAI", _FakeChatOpenAI)
    def test_generation_stops_after_first_valid_candidate(self):
        program = self.dsl.parse_str_to_node("DEF run m( move m)")
        generator = LLMProgramGenerator(
            0,
            "DoorKey",
            self.dsl,
            1,
            llm_provider="ollama",
            llm_batch_size=1,
        )
        with mock.patch.object(
            generator, "_parse_response", return_value=(program, [])
        ):
            programs, generation_log = generator._generate_programs(
                "system", "user", "python_to_dsl"
            )

        self.assertEqual(len(programs), 1)
        self.assertEqual(len(_FakeChatOpenAI.calls), 1)
        self.assertEqual(len(generation_log["record_list"][0]["llm_response"]), 1)

    def test_openai_provider_requires_key(self):
        generator = LLMProgramGenerator(
            0, "DoorKey", self.dsl, 1, llm_provider="openai"
        )
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "OPENAI_KEY"):
                generator._call_llm("system", "user", 1, 0)

    def test_event_reporter_only_receives_new_global_bests(self):
        program = self.dsl.parse_str_to_node("DEF run m( move m)")
        with tempfile.TemporaryDirectory() as directory:
            event_path = Path(directory) / "events.jsonl"
            reporter = EventReporter(
                str(event_path), "test-run", "DoorKey", 0, {"task": "DoorKey"}
            )
            search = HillClimbing(1)
            search.set_event_reporter(reporter)
            task = _Task([0.5, 0.25, 0.75])

            for _ in range(3):
                search.record_evaluate_program(program, [task], self.dsl, "Search")

            events = [
                json.loads(line)
                for line in event_path.read_text().splitlines()
                if json.loads(line)["event"] == "best_updated"
            ]
            self.assertEqual([event["reward"] for event in events], [0.5, 0.75])
            self.assertEqual(events[-1]["program_num"], 3)
            self.assertEqual(events[-1]["source_type"], "Search")
            self.assertIn("def run", events[-1]["python_program"])


if __name__ == "__main__":
    unittest.main()
