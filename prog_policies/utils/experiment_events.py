from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tqdm import tqdm

from prog_policies.utils.indent import node_to_indent_python


class EventReporter:
    """Append-only structured event stream used by the optional Gradio monitor."""

    def __init__(
        self,
        path: str | None,
        run_id: str,
        task: str,
        seed: int,
        args: dict[str, Any],
    ) -> None:
        self.path = Path(path).resolve() if path else None
        self.run_id = run_id
        self.task = task
        self.seed = seed
        self.args = args
        self._lock = threading.Lock()
        self._failed = False
        self._progress_bar = None
        self._last_progress_event = 0.0

    @classmethod
    def from_env(cls, args: Any) -> "EventReporter":
        args_dict = dict(vars(args))
        return cls(
            os.getenv("LLM_GS_EVENT_FILE"),
            os.getenv("LLM_GS_RUN_ID", f"terminal-{args_dict.get('seed', 0)}"),
            args_dict.get("task", "unknown"),
            int(args_dict.get("seed", 0)),
            args_dict,
        )

    @property
    def enabled(self) -> bool:
        return self.path is not None

    def emit(self, event: str, **payload: Any) -> None:
        if self.path is None:
            return
        item = {
            "schema_version": 1,
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "task": self.task,
            "seed": self.seed,
            **payload,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(item, ensure_ascii=True, default=str)
        with self._lock, self.path.open("a", encoding="utf-8") as stream:
            stream.write(encoded + "\n")
            stream.flush()

    def run_started(self, entrypoint: str) -> None:
        self.emit("run_started", entrypoint=entrypoint, args=self.args)

    def llm_request_started(self, **payload: Any) -> None:
        self.emit("llm_request_started", **payload)

    def llm_request_completed(self, **payload: Any) -> None:
        self.emit("llm_request_completed", **payload)

    def candidate_generated(self, program, candidate_index: int, target: int, dsl) -> None:
        self.emit(
            "candidate_generated",
            phase="LLM Preview",
            candidate_index=int(candidate_index),
            target=int(target),
            dsl_program=dsl.parse_node_to_str(program),
            python_program=node_to_indent_python(program),
        )

    def candidate_rejected(self, **payload: Any) -> None:
        self.emit("candidate_rejected", **payload)

    def best_updated(self, program, reward: float, program_num: int, source_type: str, dsl) -> None:
        source_type = source_type or "Search"
        self.emit(
            "best_updated",
            phase=source_type,
            source_type=source_type,
            program_num=int(program_num),
            reward=float(reward),
            dsl_program=dsl.parse_node_to_str(program),
            python_program=node_to_indent_python(program),
        )

    def evaluation_progress(
        self,
        program_num: int,
        best_reward: float,
        phase: str,
    ) -> None:
        maximum = max(1, int(self.args.get("max_program_nums", program_num or 1)))
        displayed = min(int(program_num), maximum)
        if self._progress_bar is None:
            force = os.getenv("LLM_GS_FORCE_PROGRESS") == "1"
            self._progress_bar = tqdm(
                total=maximum,
                initial=displayed,
                desc="Programs evaluated",
                unit="program",
                dynamic_ncols=True,
                disable=not (force or sys.stderr.isatty()),
            )
        elif displayed > self._progress_bar.n:
            self._progress_bar.update(displayed - self._progress_bar.n)
        self._progress_bar.set_postfix(
            seed=self.seed,
            phase=phase or "Search",
            best=f"{best_reward:.6f}",
            refresh=True,
        )

        now = time.monotonic()
        if now - self._last_progress_event >= 1.0 or displayed >= maximum:
            self._last_progress_event = now
            self.emit(
                "evaluation_progress",
                phase=phase or "Search",
                program_num=int(program_num),
                max_program_nums=maximum,
                best_reward=float(best_reward),
            )

    def process_exited(self, exit_code: int, stop_requested: bool) -> None:
        self.emit(
            "process_exited",
            exit_code=int(exit_code),
            stop_requested=bool(stop_requested),
        )

    def _close_progress(self) -> None:
        if self._progress_bar is not None:
            self._progress_bar.close()
            self._progress_bar = None

    def run_finished(self, best_reward: float | None = None, program_num: int | None = None) -> None:
        self._close_progress()
        self.emit("run_finished", best_reward=best_reward, program_num=program_num)

    def run_failed(self, error: BaseException, trace: str | None = None) -> None:
        if self._failed:
            return
        self._failed = True
        self._close_progress()
        self.emit(
            "run_failed",
            error_type=type(error).__name__,
            error=str(error),
            traceback=trace or "".join(traceback.format_exception(type(error), error, error.__traceback__)),
        )

    def install_exception_hook(self) -> None:
        previous_hook = sys.excepthook

        def report_exception(exc_type, exc_value, exc_traceback):
            self.run_failed(
                exc_value,
                "".join(traceback.format_exception(exc_type, exc_value, exc_traceback)),
            )
            previous_hook(exc_type, exc_value, exc_traceback)

        sys.excepthook = report_exception
