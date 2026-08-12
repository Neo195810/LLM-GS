import json
import io
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from prog_policies.karel import KarelDSL
from prog_policies.minigrid.dsl import MinigridDSL
from prog_policies.runtime import create_replay_environment
from prog_policies.utils.replay import load_historical_events, render_program_gif


class ReplayTests(unittest.TestCase):
    def test_historical_log_and_karel_gif(self):
        dsl_program = "DEF run m( move m)"
        content = {
            "args": {"task": "DoorKey", "seed": 0, "num_envs": 1},
            "seed": 0,
            "record": {"1": 0.25, "4": 0.5},
            "program_record": {
                "1": {"type": "LLM", "program": dsl_program},
                "4": {"type": "Search", "program": dsl_program},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "log.json"
            log_path.write_text(json.dumps(content))
            events = load_historical_events(log_path)
            gif_path = render_program_gif(
                "DoorKey", dsl_program, 0, directory, content["args"], max_steps=8
            )

            self.assertEqual(len(events), 2)
            self.assertEqual(events[-1]["reward"], 0.5)
            self.assertIn("def run", events[-1]["python_program"])
            self.assertTrue(gif_path.is_file())

    def test_minigrid_trace_does_not_increment_evaluation_counter(self):
        for task in ("LavaGap", "PutNear", "RedBlueDoor"):
            with self.subTest(task=task):
                environment, dsl = create_replay_environment(task, 0)
                program = dsl.parse_str_to_node("DEF run m( left m)")
                before = environment.program_num
                frames = environment.trace_program(program, max_steps=8)

                self.assertGreaterEqual(len(frames), 2)
                self.assertEqual(environment.program_num, before)
                self.assertEqual(frames[0].mode, "RGB")

    def test_direct_dsl_imports_are_stable(self):
        self.assertIsNotNone(KarelDSL())
        self.assertIsNotNone(MinigridDSL())


class GradioUtilityTests(unittest.TestCase):
    def test_presets_and_app_smoke(self):
        import gradio_utility

        presets = gradio_utility.ExperimentManager.discover_presets()
        self.assertEqual(len(presets), 58)
        self.assertIn("Python / LLM-GS main", presets)
        self.assertIn("Shell / scripts/LLM-GS/run_DoorKey.sh", presets)
        app = gradio_utility.build_app()
        config = app.get_config_file()
        components = config["components"]
        terminal = next(
            component for component in components
            if component.get("props", {}).get("label") == "Terminal output"
        )
        progress = next(
            component for component in components
            if component.get("props", {}).get("label") == "Live progress"
        )
        timer_values = sorted(
            component["props"]["value"]
            for component in components
            if component["type"] == "timer"
        )

        self.assertFalse(terminal["props"]["autoscroll"])
        self.assertFalse(progress["props"]["autoscroll"])
        self.assertEqual(timer_values, [1.0, 1.0, 3.0])
        self.assertIn("overflow-anchor: none", app.css)

    def test_progress_explains_pre_evaluation_and_early_exit(self):
        import gradio_utility

        request = {
            "event": "llm_request_started",
            "batch_number": 2,
            "total_batches": 3,
        }
        generating = gradio_utility._progress_message([request], [], "Live run | running")
        exited = gradio_utility._progress_message(
            [], [], "Live run | finished with exit code -15"
        )

        self.assertIn("2/3", generating)
        self.assertIn("tqdm", generating)
        self.assertIn("ended before", exited)

    def test_terminal_view_collapses_tqdm_redraws(self):
        import gradio_utility

        content = "start\nprogress 1\rprogress 2\rprogress 3\ndone\n"
        rendered = gradio_utility._terminal_view(content)

        self.assertNotIn("progress 1", rendered)
        self.assertNotIn("progress 2", rendered)
        self.assertIn("progress 3", rendered)

    def test_latest_progress_tracks_sixty_tqdm_redraws(self):
        import gradio_utility

        redraws = "".join(
            f"Programs evaluated {index}/64 | best=0.5\r" for index in range(1, 61)
        )

        self.assertEqual(
            gradio_utility._latest_progress(redraws),
            "Programs evaluated 60/64 | best=0.5",
        )

    def test_manager_tees_child_output_and_reaps_process(self):
        import gradio_utility

        command = [
            sys.executable,
            "-u",
            "-c",
            "import sys; print('child-out'); print('child-err', file=sys.stderr)",
        ]
        with tempfile.TemporaryDirectory(dir=gradio_utility.REPO_ROOT) as directory:
            runs_root = Path(directory) / "runs"
            manager = gradio_utility.ExperimentManager()
            captured = io.StringIO()
            with mock.patch.object(gradio_utility, "RUNS_ROOT", runs_root), mock.patch.object(
                gradio_utility.ExperimentManager,
                "discover_presets",
                return_value={"Fake": command},
            ), mock.patch.object(
                gradio_utility.ExperimentManager,
                "_needs_ollama",
                return_value=False,
            ), redirect_stdout(captured):
                manager.start("Fake", "")
                manager.monitor_thread.join(timeout=10)

            log = manager.stdout_file.read_text(encoding="utf-8")
            events = [json.loads(line) for line in manager.event_file.read_text().splitlines()]
            self.assertIn("child-out", captured.getvalue())
            self.assertIn("child-err", captured.getvalue())
            self.assertIn("child-out", log)
            self.assertIn("child-err", log)
            self.assertEqual(manager.process.returncode, 0)
            self.assertEqual(events[-1]["event"], "process_exited")

    def test_split_pollers_skip_unchanged_and_hidden_outputs(self):
        import gradio_utility

        original_manager = gradio_utility.MANAGER
        try:
            gradio_utility.MANAGER = gradio_utility.ExperimentManager()
            gradio_utility.MANAGER.source_label = "No run selected"

            first_status = gradio_utility.poll_status("run", {})
            second_status = gradio_utility.poll_status("run", first_status[-1])
            self.assertTrue(
                all(value == gradio_utility.gr.skip() for value in second_status)
            )

            first_terminal = gradio_utility.poll_terminal("run", "")
            second_terminal = gradio_utility.poll_terminal("run", first_terminal[-1])
            self.assertTrue(
                all(value == gradio_utility.gr.skip() for value in second_terminal)
            )

            hidden_visuals = gradio_utility.poll_visuals(0, None, "run", {})
            self.assertEqual(len(hidden_visuals), 9)
            self.assertTrue(
                all(value == gradio_utility.gr.skip() for value in hidden_visuals)
            )

            first_visuals = gradio_utility.poll_visuals(0, None, "best", {})
            second_visuals = gradio_utility.poll_visuals(
                0, None, "best", first_visuals[-1]
            )
            self.assertTrue(
                all(value == gradio_utility.gr.skip() for value in second_visuals)
            )
        finally:
            gradio_utility.MANAGER = original_manager

    def test_visual_event_renders_gif_only_once(self):
        import gradio_utility

        event = {
            "event": "candidate_generated",
            "timestamp": "2026-08-12T00:00:00+00:00",
            "candidate_index": 1,
            "target": 1,
            "dsl_program": "DEF run m( move m)",
            "python_program": "def run():\n    move()",
            "args": {"task": "DoorKey", "num_envs": 1},
        }
        manager = mock.Mock()
        manager.source_label = "Live run"
        manager.refresh_events.return_value = [event]
        manager.status.return_value = "Live run | running"

        original_manager = gradio_utility.MANAGER
        try:
            gradio_utility.MANAGER = manager
            with mock.patch.object(
                gradio_utility, "_render_event", return_value=("preview.gif", "")
            ) as render:
                first = gradio_utility.poll_visuals(0, None, "best", {})
                selected_choice = first[3]["value"]
                second = gradio_utility.poll_visuals(
                    0, selected_choice, "best", first[-1]
                )

            render.assert_called_once()
            self.assertEqual(first[6], "preview.gif")
            self.assertTrue(
                all(value == gradio_utility.gr.skip() for value in second)
            )
        finally:
            gradio_utility.MANAGER = original_manager


if __name__ == "__main__":
    unittest.main()
