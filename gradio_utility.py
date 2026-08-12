from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import gradio as gr
import pandas as pd
from PIL import Image, ImageDraw

from prog_policies.utils.replay import load_historical_events, render_program_gif


REPO_ROOT = Path(__file__).resolve().parent
RUNS_ROOT = REPO_ROOT / "output" / "ui_runs"
OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3-coder:30b"
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _json_request(path: str, timeout: float = 2.0) -> dict[str, Any]:
    with urllib.request.urlopen(f"{OLLAMA_URL}{path}", timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def shutil_which(command: str) -> str | None:
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(directory) / command
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def ollama_executable() -> str | None:
    executable = shutil_which("ollama")
    if executable:
        return executable
    user_install = Path.home() / ".local" / "bin" / "ollama"
    if user_install.is_file() and os.access(user_install, os.X_OK):
        return str(user_install)
    return None


def _terminal_view(content: str, limit: int = 32000) -> str:
    content = ANSI_ESCAPE.sub("", content)
    # tqdm redraws one line with carriage returns. Keep only the latest frame in the UI.
    content = re.sub(r"[^\n\r]*\r", "", content)
    return content[-limit:]


class ExperimentManager:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.output_lock = threading.Lock()
        self.process: subprocess.Popen | None = None
        self.ollama_process: subprocess.Popen | None = None
        self.output_thread: threading.Thread | None = None
        self.monitor_thread: threading.Thread | None = None
        self.heartbeat_thread: threading.Thread | None = None
        self.heartbeat_stop = threading.Event()
        self.stdout_stream = None
        self.run_id: str | None = None
        self.run_dir: Path | None = None
        self.event_file: Path | None = None
        self.stdout_file: Path | None = None
        self.events: list[dict[str, Any]] = []
        self.source_label = "No run selected"
        self.stop_requested = False
        self.started_at = 0.0
        self.last_child_output_at = 0.0
        self._ollama_cache = "Ollama status pending"
        self._ollama_cache_at = 0.0

    @staticmethod
    def discover_presets() -> dict[str, list[str]]:
        presets = {
            "Python / LLM-GS main": [sys.executable, "scripts/main.py"],
            "Python / Baseline": [sys.executable, "scripts/baseline.py"],
            "Python / LLM revision": [sys.executable, "scripts/revision.py"],
        }
        for script in sorted((REPO_ROOT / "scripts").rglob("*.sh")):
            relative = script.relative_to(REPO_ROOT).as_posix()
            presets[f"Shell / {relative}"] = ["bash", relative]
        return presets

    @staticmethod
    def discover_history() -> list[str]:
        paths = list((REPO_ROOT / "output").rglob("log.json"))
        paths.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return [path.relative_to(REPO_ROOT).as_posix() for path in paths]

    def ollama_status(self, force: bool = False) -> str:
        now = time.monotonic()
        if not force and now - self._ollama_cache_at < 10:
            return self._ollama_cache
        try:
            running = _json_request("/api/ps").get("models", [])
            selected = next(
                (model for model in running if model.get("name") == DEFAULT_MODEL), None
            )
            if selected:
                size = int(selected.get("size", 0))
                vram = int(selected.get("size_vram", 0))
                offload = round(vram / size * 100) if size else 0
                context = selected.get("context_length", "?")
                status = (
                    f"Ollama online | `{DEFAULT_MODEL}` | GPU {offload}% | context {context}"
                )
            else:
                models = {
                    model.get("name") for model in _json_request("/api/tags").get("models", [])
                }
                model_state = "ready" if DEFAULT_MODEL in models else "not downloaded"
                status = f"Ollama online | `{DEFAULT_MODEL}` | {model_state}"
        except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
            status = "Ollama offline"
        self._ollama_cache = status
        self._ollama_cache_at = now
        return status

    def ensure_ollama(self) -> None:
        try:
            models = {
                model.get("name") for model in _json_request("/api/tags").get("models", [])
            }
            if DEFAULT_MODEL not in models:
                raise RuntimeError(
                    f"Ollama is running, but {DEFAULT_MODEL} is not downloaded. "
                    f"Run: ollama pull {DEFAULT_MODEL}"
                )
            return
        except (urllib.error.URLError, TimeoutError):
            pass

        executable = ollama_executable()
        if executable is None:
            raise RuntimeError("Ollama is not installed. Run the documented install step first.")

        RUNS_ROOT.mkdir(parents=True, exist_ok=True)
        log_stream = (RUNS_ROOT / "ollama.log").open("ab", buffering=0)
        env = os.environ.copy()
        env["OLLAMA_CONTEXT_LENGTH"] = "8192"
        env["OLLAMA_NUM_PARALLEL"] = "1"
        self.ollama_process = subprocess.Popen(
            [executable, "serve"],
            cwd=REPO_ROOT,
            env=env,
            stdout=log_stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                models = {
                    model.get("name")
                    for model in _json_request("/api/tags").get("models", [])
                }
                if DEFAULT_MODEL not in models:
                    raise RuntimeError(
                        f"Ollama is running, but {DEFAULT_MODEL} is not downloaded."
                    )
                self.ollama_status(force=True)
                return
            except urllib.error.URLError:
                time.sleep(0.5)
        raise RuntimeError("Ollama did not become ready within 20 seconds.")

    @staticmethod
    def _needs_ollama(command: list[str]) -> bool:
        joined = " ".join(command)
        return any(
            marker in joined
            for marker in ("scripts/main.py", "scripts/revision.py", "LLM-GS", "LLM-Revision")
        )

    def _write_output(self, data: bytes, child_output: bool = False) -> None:
        if not data:
            return
        with self.output_lock:
            if self.stdout_stream is not None and not self.stdout_stream.closed:
                self.stdout_stream.write(data)
                self.stdout_stream.flush()
            target = getattr(sys.stdout, "buffer", sys.stdout)
            try:
                target.write(data)
            except TypeError:
                target.write(data.decode("utf-8", errors="replace"))
            target.flush()
        if child_output:
            self.last_child_output_at = time.monotonic()

    def _diagnostic(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._write_output(f"[gradio {timestamp}] {message}\n".encode("utf-8"))

    def _pump_output(self, process: subprocess.Popen) -> None:
        if process.stdout is None:
            return
        while True:
            chunk = process.stdout.read(4096)
            if not chunk:
                break
            self._write_output(chunk, child_output=True)
        process.stdout.close()

    def _append_process_event(self, code: int) -> None:
        if self.event_file is None:
            return
        event = {
            "schema_version": 1,
            "event": "process_exited",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "exit_code": int(code),
            "stop_requested": self.stop_requested,
        }
        with self.event_file.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=True) + "\n")

    def _heartbeat(self, process: subprocess.Popen) -> None:
        while not self.heartbeat_stop.wait(30):
            if process.poll() is not None:
                return
            now = time.monotonic()
            elapsed = now - self.started_at
            quiet = now - self.last_child_output_at
            self._diagnostic(
                f"PID {process.pid} alive | elapsed {elapsed:.0f}s | "
                f"last task output {quiet:.0f}s ago | {self.ollama_status()}"
            )

    def _monitor(self, process: subprocess.Popen) -> None:
        code = process.wait()
        self.heartbeat_stop.set()
        if self.heartbeat_thread is not None:
            self.heartbeat_thread.join(timeout=2)
        if self.output_thread is not None:
            self.output_thread.join(timeout=5)
        self._append_process_event(code)
        elapsed = time.monotonic() - self.started_at
        self._diagnostic(f"PID {process.pid} exited with code {code} after {elapsed:.1f}s")
        with self.output_lock:
            if self.stdout_stream is not None and not self.stdout_stream.closed:
                self.stdout_stream.close()

    def start(self, preset: str, extra_args: str) -> str:
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                raise RuntimeError("A job is already running. Stop it before starting another one.")

            presets = self.discover_presets()
            if preset not in presets:
                raise ValueError(f"Unknown command preset: {preset}")
            command = list(presets[preset])
            if extra_args.strip():
                command.extend(shlex.split(extra_args))
            if self._needs_ollama(command):
                self.ensure_ollama()

            now = datetime.now().strftime("%Y%m%d-%H%M%S")
            self.run_id = f"{now}-{uuid.uuid4().hex[:8]}"
            self.run_dir = RUNS_ROOT / self.run_id
            self.run_dir.mkdir(parents=True, exist_ok=False)
            self.event_file = self.run_dir / "events.jsonl"
            self.stdout_file = self.run_dir / "stdout.log"
            self.events = []
            self.source_label = f"Live run: {self.run_id}"
            self.stop_requested = False
            self.started_at = time.monotonic()
            self.last_child_output_at = self.started_at
            self.heartbeat_stop = threading.Event()

            env = os.environ.copy()
            env.update(
                {
                    "LLM_GS_EVENT_FILE": str(self.event_file),
                    "LLM_GS_RUN_ID": self.run_id,
                    "LLM_GS_OUTPUT_DIR": str(self.run_dir / "results"),
                    "LLM_GS_LLM_DEBUG_FILE": str(self.run_dir / "llm_debug.jsonl"),
                    "LLM_GS_FORCE_PROGRESS": "1",
                    "LLM_PROVIDER": "ollama",
                    "LLM_MODEL": DEFAULT_MODEL,
                    "LLM_BASE_URL": f"{OLLAMA_URL}/v1",
                    "LLM_BATCH_SIZE": "1",
                    "LLM_MAX_TOKENS": "1024",
                    "LLM_REQUEST_TIMEOUT": "300",
                    "PYTHONUNBUFFERED": "1",
                }
            )
            conda_prefix = env.get("CONDA_PREFIX")
            if conda_prefix:
                libstdcpp = Path(conda_prefix) / "lib" / "libstdc++.so.6"
                if libstdcpp.exists():
                    env["LD_PRELOAD"] = str(libstdcpp)

            (self.run_dir / "command.json").write_text(
                json.dumps({"command": command, "preset": preset}, indent=2),
                encoding="utf-8",
            )
            self.stdout_stream = self.stdout_file.open("wb", buffering=0)
            self._diagnostic(f"command: {shlex.join(command)}")
            self._diagnostic(f"run directory: {self.run_dir}")
            self._diagnostic(f"task log: {self.stdout_file}")
            self._diagnostic(f"LLM debug log: {self.run_dir / 'llm_debug.jsonl'}")

            self.process = subprocess.Popen(
                command,
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
                start_new_session=True,
            )
            process = self.process
            self._diagnostic(f"started PID {process.pid}")
            self.output_thread = threading.Thread(
                target=self._pump_output, args=(process,), daemon=True
            )
            self.heartbeat_thread = threading.Thread(
                target=self._heartbeat, args=(process,), daemon=True
            )
            self.monitor_thread = threading.Thread(
                target=self._monitor, args=(process,), daemon=True
            )
            self.output_thread.start()
            self.heartbeat_thread.start()
            self.monitor_thread.start()
            return f"Started `{self.run_id}` with PID {process.pid}."

    def stop(self) -> str:
        with self.lock:
            if self.process is None or self.process.poll() is not None:
                return "No active job."
            self.stop_requested = True
            process = self.process
            self._diagnostic(f"sending SIGTERM to process group {process.pid}")
            os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=8)
            return f"Stopped run `{self.run_id}` cleanly."
        except subprocess.TimeoutExpired:
            self._diagnostic(f"SIGTERM timed out; sending SIGKILL to {process.pid}")
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=3)
            return f"Force-stopped run `{self.run_id}` after the shutdown timeout."

    def refresh_events(self) -> list[dict[str, Any]]:
        with self.lock:
            if self.event_file and self.event_file.exists():
                events = []
                for line in self.event_file.read_text(encoding="utf-8").splitlines():
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                self.events = events
            return list(self.events)

    def status(self) -> str:
        with self.lock:
            if self.process is None:
                return self.source_label
            code = self.process.poll()
            if code is None:
                return f"{self.source_label} | running (PID {self.process.pid})"
            if self.stop_requested:
                return f"{self.source_label} | stopped (exit {code})"
            return f"{self.source_label} | finished with exit code {code}"

    def stdout_tail(self, limit: int = 64000) -> str:
        return _terminal_view(self.stdout_raw_tail(limit))

    def stdout_raw_tail(self, limit: int = 64000) -> str:
        with self.output_lock:
            if not self.stdout_file or not self.stdout_file.exists():
                return ""
            content = self.stdout_file.read_text(encoding="utf-8", errors="replace")
        return content[-limit:]

    def args_for_event(self, selected: dict[str, Any]) -> dict[str, Any]:
        if selected.get("args"):
            return selected["args"]
        for event in reversed(self.events):
            if event.get("event") == "run_started":
                return event.get("args", {})
        return {"task": selected.get("task"), "num_envs": 32}


MANAGER = ExperimentManager()


def _choice_label(index: int, event: dict[str, Any]) -> str:
    return (
        f"{index} | seed {event.get('seed')} | #{event.get('program_num')} | "
        f"reward {event.get('reward', 0):.6f}"
    )


def _reward_chart(events: list[dict[str, Any]]) -> Image.Image:
    width, height = 960, 340
    left, top, right, bottom = 74, 32, 28, 54
    chart = Image.new("RGB", (width, height), "#f8f5ed")
    draw = ImageDraw.Draw(chart)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), 18, outline="#d8d0c0", width=2)
    draw.text((left, 10), "Best reward progression", fill="#16211c")
    plot_right = width - right
    plot_bottom = height - bottom
    draw.line((left, top, left, plot_bottom), fill="#6f786f", width=2)
    draw.line((left, plot_bottom, plot_right, plot_bottom), fill="#6f786f", width=2)
    if not events:
        draw.text((left + 18, top + 24), "Waiting for the first best-reward event...", fill="#6f786f")
        return chart

    program_numbers = [int(event["program_num"]) for event in events]
    rewards = [float(event["reward"]) for event in events]
    x_min, x_max = min(program_numbers), max(program_numbers)
    y_min, y_max = min(0.0, min(rewards)), max(1.0, max(rewards))
    x_span, y_span = max(1, x_max - x_min), max(1e-9, y_max - y_min)
    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = plot_bottom - int((plot_bottom - top) * fraction)
        reward = y_min + y_span * fraction
        draw.line((left, y, plot_right, y), fill="#e2ddd2", width=1)
        draw.text((12, y - 7), f"{reward:.2f}", fill="#59625c")

    colors = ["#df5b32", "#167f72", "#d19328", "#356aa0", "#8a5a44"]
    grouped: dict[int, list[tuple[int, float]]] = {}
    for event in events:
        grouped.setdefault(int(event.get("seed", 0)), []).append(
            (int(event["program_num"]), float(event["reward"]))
        )
    for color_index, (seed, points) in enumerate(sorted(grouped.items())):
        color = colors[color_index % len(colors)]
        coordinates = [
            (
                left + int((program_num - x_min) / x_span * (plot_right - left)),
                plot_bottom - int((reward - y_min) / y_span * (plot_bottom - top)),
            )
            for program_num, reward in points
        ]
        if len(coordinates) > 1:
            draw.line(coordinates, fill=color, width=4)
        for x, y in coordinates:
            draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=color, outline="#fff", width=2)
        draw.text((plot_right - 85 + color_index * 5, 10 + color_index * 16), f"seed {seed}", fill=color)
    draw.text((left - 8, plot_bottom + 16), str(x_min), fill="#59625c")
    draw.text((plot_right - 24, plot_bottom + 16), str(x_max), fill="#59625c")
    draw.text((width // 2 - 42, plot_bottom + 34), "program number", fill="#39433d")
    return chart


def _event_args(event: dict[str, Any]) -> dict[str, Any]:
    return event.get("args") or MANAGER.args_for_event(event)


def _render_event(
    event: dict[str, Any], environment_index: int, output_dir: Path | None = None
) -> tuple[str | None, str]:
    if not event.get("dsl_program"):
        return None, "Replay unavailable: this event has no DSL program."
    trace_dir = output_dir or (MANAGER.run_dir or RUNS_ROOT / "replay_cache") / "traces"
    try:
        path = render_program_gif(
            event["task"],
            event["dsl_program"],
            environment_index,
            trace_dir,
            _event_args(event),
        )
        return str(path), ""
    except Exception as error:
        return None, f"Replay failed: {type(error).__name__}: {error}"


def _events_table(events: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "seed": event.get("seed"),
                "program_num": event.get("program_num"),
                "reward": event.get("reward"),
                "phase": event.get("phase"),
            }
            for event in events
        ],
        columns=["seed", "program_num", "reward", "phase"],
    )


def _progress_message(
    all_events: list[dict[str, Any]],
    best_events: list[dict[str, Any]],
    run_status: str,
    replay_error: str = "",
) -> str:
    failed = next((event for event in reversed(all_events) if event.get("event") == "run_failed"), None)
    if failed:
        return (
            "### Experiment progress\n"
            f"**Failed:** `{failed.get('error_type', 'Error')}`: {failed.get('error', 'Unknown error')}."
        )
    if best_events:
        latest = best_events[-1]
        message = (
            "### Experiment progress\n"
            f"Best reward **{float(latest.get('reward', 0)):.6f}** at program "
            f"**#{latest.get('program_num')}** ({latest.get('phase', 'Search')})."
        )
        return message + (f"\n\n**{replay_error}**" if replay_error else "")
    preview = next(
        (event for event in reversed(all_events) if event.get("event") == "candidate_generated"), None
    )
    if preview:
        message = (
            "### Experiment progress\n"
            f"Previewing valid LLM candidate **{preview.get('candidate_index')}/{preview.get('target')}**. "
            "It has not been reward-evaluated yet."
        )
        return message + (f"\n\n**{replay_error}**" if replay_error else "")
    request = next(
        (event for event in reversed(all_events) if event.get("event", "").startswith("llm_request_")), None
    )
    if request:
        if request["event"] == "llm_request_started":
            return (
                "### Experiment progress\n"
                f"Ollama request **{request.get('batch_number')}/{request.get('total_batches')}** "
                "is generating. Watch the elapsed tqdm spinner in the terminal."
            )
        return (
            "### Experiment progress\n"
            f"Ollama request completed in **{float(request.get('duration_seconds', 0)):.1f}s**; "
            "parsing its program now."
        )
    if "finished with exit code" in run_status or "stopped" in run_status:
        return "### Experiment progress\nThe run ended before producing a best-reward event."
    if "running" in run_status:
        return "### Experiment progress\nInitialising the task and local model."
    return "### Experiment progress\nStart an experiment to generate and evaluate a program."


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _latest_progress(content: str) -> str:
    content = ANSI_ESCAPE.sub("", content)
    frames = [frame.strip() for frame in re.split(r"[\r\n]+", content) if frame.strip()]
    markers = (
        "Programs evaluated",
        "Valid LLM programs",
        "Ollama request",
        "LLM request",
        "LLM candidate",
        "Task:",
        "[gradio",
    )
    for frame in reversed(frames):
        if any(marker in frame for marker in markers):
            return frame[-300:]
    return frames[-1][-300:] if frames else "Waiting for experiment output."


def poll_status(active_tab: str, status_state: dict[str, Any] | None):
    state = dict(status_state or {})
    run_status = MANAGER.status()
    ollama = MANAGER.ollama_status()
    latest_progress = _latest_progress(MANAGER.stdout_raw_tail())
    run_output = run_status if state.get("run_status") != run_status else gr.skip()
    ollama_output = ollama if state.get("ollama") != ollama else gr.skip()
    if active_tab == "run" and (
        state.get("active_tab") != "run" or state.get("latest_progress") != latest_progress
    ):
        progress_output = latest_progress
    else:
        progress_output = gr.skip()
    new_state = {
        "run_status": run_status,
        "ollama": ollama,
        "latest_progress": latest_progress,
        "active_tab": active_tab,
    }
    state_output = new_state if new_state != state else gr.skip()
    return run_output, ollama_output, progress_output, state_output


def poll_terminal(active_tab: str, terminal_hash: str):
    if active_tab != "run":
        return gr.skip(), gr.skip()
    terminal = MANAGER.stdout_tail()
    current_hash = _digest(terminal)
    if current_hash == terminal_hash:
        return gr.skip(), gr.skip()
    return terminal, current_hash


def poll_visuals(
    environment_index: int,
    current_choice: str | None,
    active_tab: str,
    visual_state: dict[str, Any] | None,
):
    if active_tab != "best":
        return tuple(gr.skip() for _ in range(9))

    state = dict(visual_state or {})
    previous_state = dict(state)
    all_events = MANAGER.refresh_events()
    best_events = [event for event in all_events if event.get("event") == "best_updated"]
    previews = [event for event in all_events if event.get("event") == "candidate_generated"]
    run_status = MANAGER.status()

    choices = [_choice_label(index, event) for index, event in enumerate(best_events)]
    previous_count = int(state.get("best_count", 0))
    if choices:
        if len(best_events) > previous_count or current_choice not in choices:
            selected_choice = choices[-1]
        else:
            selected_choice = current_choice
    else:
        selected_choice = None

    visual_revision = _digest(
        {
            "source": MANAGER.source_label,
            "best": [(event.get("timestamp"), event.get("program_num")) for event in best_events],
            "preview": [(event.get("timestamp"), event.get("candidate_index")) for event in previews],
            "environment": int(environment_index),
            "choice": selected_choice,
        }
    )
    replay_error = state.get("replay_error", "")
    heavy_changed = state.get("visual_revision") != visual_revision
    if heavy_changed:
        maximum = 31
        latest_event = best_events[-1] if best_events else (previews[-1] if previews else None)
        if latest_event:
            maximum = max(0, int(_event_args(latest_event).get("num_envs", 32)) - 1)
        selected_environment = min(int(environment_index), maximum)
        if choices:
            selected = best_events[int(selected_choice.split("|", 1)[0].strip())]
        else:
            selected_choice = None
            selected = previews[-1] if previews else None
        if selected:
            image, replay_error = _render_event(selected, selected_environment)
            dsl_program = selected.get("dsl_program", "")
            python_program = selected.get("python_program", "")
        else:
            image, replay_error, dsl_program, python_program = None, "", "", ""
        heavy_outputs = (
            _reward_chart(best_events),
            _events_table(best_events),
            gr.update(choices=choices, value=selected_choice),
            dsl_program,
            python_program,
            image,
            gr.update(maximum=maximum, value=selected_environment),
        )
    else:
        heavy_outputs = tuple(gr.skip() for _ in range(7))

    progress = _progress_message(all_events, best_events, run_status, replay_error)
    progress_output = progress if state.get("progress") != progress else gr.skip()
    state.update(
        {
            "visual_revision": visual_revision,
            "best_count": len(best_events),
            "replay_error": replay_error,
            "progress": progress,
        }
    )
    state_output = state if state != previous_state else gr.skip()
    return (
        progress_output,
        *heavy_outputs,
        state_output,
    )


def start_job(preset: str, extra_args: str) -> str:
    try:
        return MANAGER.start(preset, extra_args)
    except Exception as error:
        return f"Start failed: {error}"


def stop_job() -> str:
    try:
        return MANAGER.stop()
    except Exception as error:
        return f"Stop failed: {error}"


def refresh_history():
    choices = MANAGER.discover_history()
    return gr.update(choices=choices, value=choices[0] if choices else None)


def _history_outputs(events: list[dict[str, Any]], environment_index: int, choice=None):
    choices = [_choice_label(index, event) for index, event in enumerate(events)]
    selected_choice = choice if choice in choices else (choices[-1] if choices else None)
    if not selected_choice:
        return _reward_chart([]), _events_table([]), gr.update(choices=[], value=None), "", "", None, gr.update(maximum=0, value=0)
    event = events[int(selected_choice.split("|", 1)[0].strip())]
    maximum = max(0, int(event.get("args", {}).get("num_envs", 32)) - 1)
    environment_index = min(int(environment_index), maximum)
    image, _ = _render_event(event, environment_index, RUNS_ROOT / "replay_cache" / "history")
    return (
        _reward_chart(events),
        _events_table(events),
        gr.update(choices=choices, value=selected_choice),
        event.get("dsl_program", ""),
        event.get("python_program", ""),
        image,
        gr.update(maximum=maximum, value=environment_index),
    )


def load_history_view(relative_path: str, environment_index: int):
    try:
        path = (REPO_ROOT / relative_path).resolve()
        if REPO_ROOT not in path.parents or not path.is_file() or path.name != "log.json":
            raise ValueError("Select a valid repository log.json file.")
        events = load_historical_events(path)
        outputs = _history_outputs(events, environment_index)
        return f"Loaded {len(events)} best-reward events from `{relative_path}`.", events, *outputs
    except Exception as error:
        return f"History load failed: {error}", [], *_history_outputs([], 0)


def select_history_event(choice: str, environment_index: int, events: list[dict[str, Any]]):
    outputs = _history_outputs(events or [], environment_index, choice)
    return outputs[3], outputs[4], outputs[5], outputs[6]


def select_live_event(choice: str, environment_index: int):
    if not choice:
        return "", "", None
    events = [event for event in MANAGER.refresh_events() if event.get("event") == "best_updated"]
    try:
        event = events[int(choice.split("|", 1)[0].strip())]
        image, _ = _render_event(event, int(environment_index))
        return event.get("dsl_program", ""), event.get("python_program", ""), image
    except (IndexError, ValueError):
        return "", "", None


def build_app() -> gr.Blocks:
    presets = MANAGER.discover_presets()
    history = MANAGER.discover_history()
    css = """
    :root { --ink: #17211c; --accent: #df5b32; --paper: #f4f0e6; }
    html, body, .gradio-container {
        color: var(--ink) !important;
        overflow-anchor: none !important;
        scroll-behavior: auto !important;
    }
    .gradio-container { background: radial-gradient(circle at 85% 5%, #f8c66a55, transparent 28%), var(--paper); }
    .hero { border-left: 7px solid var(--accent); padding-left: 18px; color: var(--ink); }
    .status-row { min-height: 72px; height: 72px; max-height: 72px; overflow: auto; color: var(--ink); }
    .action-status { min-height: 48px; height: 48px; max-height: 48px; overflow: auto; }
    .progress-panel { min-height: 86px; height: 86px; max-height: 86px; overflow: auto; }
    .fixed-chart { min-height: 390px; height: 390px; max-height: 390px; overflow: hidden; }
    .fixed-replay { min-height: 480px; height: 480px; max-height: 480px; overflow: hidden; }
    .fixed-table { min-height: 280px; height: 280px; max-height: 280px; overflow: hidden; }
    .code-panel { min-height: 310px; height: 310px; max-height: 310px; overflow: auto; }
    .code-panel textarea { font-family: 'IBM Plex Mono', 'Courier New', monospace !important; }
    #live-progress { min-height: 78px; height: 78px; max-height: 78px; overflow: hidden; }
    #live-progress textarea { height: 38px !important; max-height: 38px !important; resize: none; overflow: hidden !important; }
    #terminal-output { min-height: 440px; height: 440px; max-height: 440px; overflow: hidden; }
    #terminal-output textarea {
        height: 390px !important;
        max-height: 390px !important;
        overflow-y: auto !important;
        resize: none;
        overflow-anchor: none !important;
    }
    """
    with gr.Blocks(title="LLM-GS Observatory", css=css) as app:
        active_tab_state = gr.State("run")
        status_state = gr.State({})
        terminal_hash_state = gr.State("")
        visual_state = gr.State({})
        history_events_state = gr.State([])
        gr.Markdown(
            "# LLM-GS Observatory\nLocal model experiments, search progress, and agent replay.",
            elem_classes=["hero"],
        )
        with gr.Row(elem_classes=["status-row"]):
            run_status = gr.Markdown("No run selected")
            ollama_status = gr.Markdown(MANAGER.ollama_status())
        action_result = gr.Markdown(
            "Ready to start an experiment.", elem_classes=["action-status"]
        )

        with gr.Tabs(selected="run"):
            with gr.Tab("Run & Monitor", id="run") as run_tab:
                with gr.Row():
                    preset = gr.Dropdown(
                        choices=list(presets), value="Python / LLM-GS main",
                        label="Command preset", scale=2
                    )
                    extra_args = gr.Textbox(
                        value="--seed 0 --task DoorKey --llm_program_num 1 --num_envs 1 --max_program_nums 64 --start_k 32 --end_k 32",
                        label="Additional CLI arguments", scale=4,
                    )
                with gr.Row():
                    start_button = gr.Button("Start experiment", variant="primary")
                    stop_button = gr.Button("Stop", variant="stop")
                live_progress = gr.Textbox(
                    value="Waiting for experiment output.", label="Live progress",
                    lines=1, max_lines=1, interactive=False, autoscroll=False,
                    elem_id="live-progress",
                )
                terminal = gr.Textbox(
                    label="Terminal output", lines=18, max_lines=18, interactive=False,
                    autoscroll=False, elem_id="terminal-output",
                )

            with gr.Tab("Best Programs", id="best") as best_tab:
                progress_status = gr.Markdown(
                    "### Experiment progress\nStart an experiment to generate and evaluate a program.",
                    elem_classes=["progress-panel"],
                )
                with gr.Row():
                    event_choice = gr.Dropdown(label="Best-reward event", scale=4)
                    environment_index = gr.Slider(
                        0, 31, value=0, step=1, label="Environment index", scale=2
                    )
                    replay_button = gr.Button("Replay selected", scale=1)
                with gr.Row():
                    reward_plot = gr.Image(
                        value=_reward_chart([]), label="Best reward progression", type="pil",
                        interactive=False, height=340, elem_classes=["fixed-chart"],
                    )
                    trace_image = gr.Image(
                        label="Agent task replay", type="filepath", height=430,
                        elem_classes=["fixed-replay"],
                    )
                best_table = gr.Dataframe(
                    headers=["seed", "program_num", "reward", "phase"], interactive=False,
                    label="Improvement history", height=240, elem_classes=["fixed-table"],
                )
                with gr.Row():
                    dsl_program = gr.Code(
                        label="DSL program", language=None, lines=14, elem_classes=["code-panel"]
                    )
                    python_program = gr.Code(
                        label="Python-like program", language="python", lines=14,
                        elem_classes=["code-panel"],
                    )

            with gr.Tab("History", id="history") as history_tab:
                with gr.Row():
                    history_path = gr.Dropdown(
                        choices=history, value=history[0] if history else None,
                        label="Existing log.json", scale=4,
                    )
                    refresh_button = gr.Button("Refresh", scale=1)
                    load_button = gr.Button("Load history", variant="primary", scale=1)
                history_result = gr.Markdown(
                    "History is independent from the active live run.",
                    elem_classes=["action-status"],
                )
                with gr.Row():
                    history_choice = gr.Dropdown(label="Historical best event", scale=4)
                    history_environment = gr.Slider(
                        0, 31, value=0, step=1, label="Environment index", scale=2
                    )
                    history_replay_button = gr.Button("Replay historical", scale=1)
                with gr.Row():
                    history_plot = gr.Image(
                        value=_reward_chart([]), label="Historical reward progression", type="pil",
                        height=340, elem_classes=["fixed-chart"],
                    )
                    history_image = gr.Image(
                        label="Historical agent replay", type="filepath", height=430,
                        elem_classes=["fixed-replay"],
                    )
                history_table = gr.Dataframe(
                    headers=["seed", "program_num", "reward", "phase"], interactive=False,
                    height=240, elem_classes=["fixed-table"],
                )
                with gr.Row():
                    history_dsl = gr.Code(
                        label="Historical DSL", lines=14, elem_classes=["code-panel"]
                    )
                    history_python = gr.Code(
                        label="Historical Python-like program", language="python", lines=14,
                        elem_classes=["code-panel"],
                    )

        start_button.click(start_job, [preset, extra_args], action_result, queue=False)
        stop_button.click(stop_job, outputs=action_result, queue=False)
        replay_button.click(
            select_live_event,
            [event_choice, environment_index],
            [dsl_program, python_program, trace_image],
            queue=False,
        )
        refresh_button.click(refresh_history, outputs=history_path, queue=False)
        load_button.click(
            load_history_view,
            [history_path, history_environment],
            [
                history_result,
                history_events_state,
                history_plot,
                history_table,
                history_choice,
                history_dsl,
                history_python,
                history_image,
                history_environment,
            ],
            queue=False,
        )
        history_choice.change(
            select_history_event,
            [history_choice, history_environment, history_events_state],
            [history_dsl, history_python, history_image, history_environment],
            queue=False,
        )
        history_replay_button.click(
            select_history_event,
            [history_choice, history_environment, history_events_state],
            [history_dsl, history_python, history_image, history_environment],
            queue=False,
        )
        run_tab.select(lambda: "run", outputs=active_tab_state, queue=False, show_progress="hidden")
        best_tab.select(lambda: "best", outputs=active_tab_state, queue=False, show_progress="hidden")
        history_tab.select(
            lambda: "history", outputs=active_tab_state, queue=False, show_progress="hidden"
        )

        status_timer = gr.Timer(1.0)
        status_timer.tick(
            poll_status,
            [active_tab_state, status_state],
            [run_status, ollama_status, live_progress, status_state],
            queue=True,
            show_progress="hidden",
            trigger_mode="always_last",
        )
        terminal_timer = gr.Timer(3.0)
        terminal_timer.tick(
            poll_terminal,
            [active_tab_state, terminal_hash_state],
            [terminal, terminal_hash_state],
            queue=True,
            show_progress="hidden",
            trigger_mode="always_last",
        )
        visual_timer = gr.Timer(1.0)
        visual_timer.tick(
            poll_visuals,
            [environment_index, event_choice, active_tab_state, visual_state],
            [
                progress_status,
                reward_plot,
                best_table,
                event_choice,
                dsl_program,
                python_program,
                trace_image,
                environment_index,
                visual_state,
            ],
            queue=True,
            show_progress="hidden",
            trigger_mode="always_last",
        )
    return app


def parse_args():
    parser = argparse.ArgumentParser(description="Monitor and replay LLM-GS experiments.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    return parser.parse_args()


if __name__ == "__main__":
    cli_args = parse_args()
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    build_app().queue(default_concurrency_limit=1).launch(
        server_name=cli_args.host,
        server_port=cli_args.port,
        share=False,
        allowed_paths=[str(RUNS_ROOT.resolve())],
        show_error=True,
    )
