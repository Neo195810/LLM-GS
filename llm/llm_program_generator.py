from __future__ import annotations

import json
import math
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List

import numpy as np
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from tqdm import tqdm

from llm.prompt_generator import PromptGenerator
from llm.utils import (
    get_program_str_from_llm_response_dsl,
    get_program_str_from_llm_response_python,
)
from prog_policies.base import BaseDSL, dsl_nodes
from prog_policies.utils import get_env_name


DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"
DEFAULT_OLLAMA_MODEL = "qwen3-coder:30b"


def _progress_enabled() -> bool:
    return os.getenv("LLM_GS_FORCE_PROGRESS") == "1" or sys.stderr.isatty()


class _RequestSpinner:
    """Show that a non-streaming model request is alive without faking token progress."""

    def __init__(self, description: str, timeout: float | None) -> None:
        self.enabled = _progress_enabled()
        self.stop_event = threading.Event()
        suffix = f", timeout={timeout:g}s" if timeout else ""
        self.bar = tqdm(
            total=None,
            desc=description,
            unit="s",
            dynamic_ncols=True,
            leave=False,
            disable=not self.enabled,
            bar_format="{desc}: {n:.0f}s elapsed [{elapsed}" + suffix + "]",
        )
        self.thread: threading.Thread | None = None

    def __enter__(self):
        if self.enabled:
            self.thread = threading.Thread(target=self._tick, daemon=True)
            self.thread.start()
        return self

    def _tick(self) -> None:
        while not self.stop_event.wait(1.0):
            self.bar.update(1)

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=2)
        self.bar.close()


class LLMProgramGenerator:
    def __init__(
        self,
        seed: int,
        task: str,
        dsl: BaseDSL,
        llm_program_num: int,
        temperature: float = 1.0,
        top_p: float = 1.0,
        action_shots: int = 0,
        perception_shots: int = 0,
        program_shots: int = 0,
        llm_provider: str = "ollama",
        llm_model: str | None = None,
        llm_base_url: str | None = None,
        llm_batch_size: int = 1,
        llm_max_attempts: int = 3,
        llm_max_tokens: int = 1024,
        llm_request_timeout: float = 300,
        event_reporter=None,
    ) -> None:
        self.seed = seed
        self.task = task
        self.env_name = get_env_name(task)
        self.dsl = dsl
        self.ratio = 1.5
        self.llm_program_num = llm_program_num
        self.llm_provider = llm_provider.lower()
        if self.llm_provider not in {"ollama", "openai"}:
            raise ValueError(f"Unsupported LLM provider: {llm_provider}")
        self.model_name = llm_model or (
            DEFAULT_OLLAMA_MODEL
            if self.llm_provider == "ollama"
            else "gpt-4-turbo-2024-04-09"
        )
        self.llm_base_url = llm_base_url or (
            DEFAULT_OLLAMA_BASE_URL if self.llm_provider == "ollama" else None
        )
        self.llm_batch_size = max(1, llm_batch_size)
        self.llm_max_attempts = max(1, llm_max_attempts)
        self.llm_max_tokens = max(0, int(llm_max_tokens))
        self.llm_request_timeout = max(0.0, float(llm_request_timeout))
        self.temperature = temperature
        self.top_p = top_p
        self.event_reporter = event_reporter
        self.request_number = 0
        debug_path = os.getenv("LLM_GS_LLM_DEBUG_FILE")
        self.debug_path = Path(debug_path).resolve() if debug_path else None

        self.np_rng = np.random.RandomState(self.seed)
        self.prompt_generator = PromptGenerator(
            self.task,
            action_shots,
            perception_shots,
            program_shots,
        )

    def _emit(self, method: str, **payload: Any) -> None:
        callback = getattr(self.event_reporter, method, None)
        if callback is not None:
            callback(**payload)

    def _write_debug(self, **payload: Any) -> None:
        if self.debug_path is None:
            return
        self.debug_path.parent.mkdir(parents=True, exist_ok=True)
        item = {"timestamp": time.time(), "task": self.task, **payload}
        with self.debug_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(item, ensure_ascii=True, default=str) + "\n")

    def _api_key(self) -> str:
        if self.llm_provider == "ollama":
            return "ollama"
        api_key = os.getenv("OPENAI_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_KEY is required when --llm_provider=openai.")
        return api_key

    def _client_args(self, batch_size: int, seed: int) -> dict[str, Any]:
        client_args: dict[str, Any] = {
            "api_key": self._api_key(),
            "model": self.model_name,
            "temperature": self.temperature,
            "n": batch_size,
            "model_kwargs": {"top_p": self.top_p, "seed": int(seed % (2**31 - 1))},
        }
        if self.llm_base_url:
            client_args["base_url"] = self.llm_base_url
        if self.llm_max_tokens:
            client_args["max_tokens"] = self.llm_max_tokens
        if self.llm_request_timeout:
            client_args["timeout"] = self.llm_request_timeout
        if self.llm_provider == "ollama":
            client_args["tiktoken_model_name"] = "gpt-3.5-turbo"
            client_args["max_retries"] = 0
        return client_args

    def _iter_llm_batches(
        self,
        system_prompt: str,
        user_prompt: str,
        llm_program_num: int,
        seed: int,
        attempt: int = 1,
    ) -> Iterator[tuple[list[str], dict[str, Any]]]:
        total_batches = math.ceil(llm_program_num / self.llm_batch_size)
        for offset in range(0, llm_program_num, self.llm_batch_size):
            batch_size = min(self.llm_batch_size, llm_program_num - offset)
            batch_number = offset // self.llm_batch_size + 1
            self.request_number += 1
            request_seed = int((seed + offset) % (2**31 - 1))
            request_info = {
                "request_number": self.request_number,
                "attempt": attempt,
                "batch_number": batch_number,
                "total_batches": total_batches,
                "batch_size": batch_size,
                "provider": self.llm_provider,
                "model": self.model_name,
                "seed": request_seed,
                "max_tokens": self.llm_max_tokens,
                "timeout": self.llm_request_timeout,
            }
            print(
                f"LLM request {batch_number}/{total_batches}: requesting "
                f"{batch_size} candidate(s) from {self.llm_provider}/{self.model_name} "
                f"(max_tokens={self.llm_max_tokens or 'unlimited'}, "
                f"timeout={self.llm_request_timeout or 'none'}s)",
                flush=True,
            )
            self._emit("llm_request_started", **request_info)
            started = time.monotonic()
            try:
                with _RequestSpinner(
                    f"Ollama request {batch_number}/{total_batches}",
                    self.llm_request_timeout or None,
                ):
                    chat_model = ChatOpenAI(
                        **self._client_args(batch_size, request_seed)
                    )
                    response = chat_model.generate(
                        [[
                            SystemMessage(content=system_prompt),
                            HumanMessage(content=user_prompt),
                        ]]
                    ).generations[0]
                responses = [generation.text for generation in response]
            except Exception as error:
                duration = time.monotonic() - started
                self._emit(
                    "llm_request_completed",
                    **request_info,
                    status="failed",
                    duration_seconds=duration,
                    error=f"{type(error).__name__}: {error}",
                )
                self._write_debug(
                    **request_info,
                    status="failed",
                    duration_seconds=duration,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    error=f"{type(error).__name__}: {error}",
                )
                print(
                    f"LLM request {batch_number}/{total_batches}: failed after "
                    f"{duration:.1f}s: {type(error).__name__}: {error}",
                    flush=True,
                )
                raise

            duration = time.monotonic() - started
            response_chars = sum(len(text) for text in responses)
            self._emit(
                "llm_request_completed",
                **request_info,
                status="completed",
                duration_seconds=duration,
                response_chars=response_chars,
            )
            print(
                f"LLM request {batch_number}/{total_batches}: completed in "
                f"{duration:.1f}s ({response_chars} chars)",
                flush=True,
            )
            yield responses, {
                **request_info,
                "duration_seconds": duration,
                "response_chars": response_chars,
            }

    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        llm_program_num: int,
        seed: int,
    ) -> str | List[str | Dict]:
        responses: list[str] = []
        for batch, _ in self._iter_llm_batches(
            system_prompt, user_prompt, llm_program_num, seed
        ):
            responses.extend(batch)
        return responses

    def _check_generation_attempts(self, attempts: int, available_programs: int) -> None:
        if attempts >= self.llm_max_attempts:
            raise RuntimeError(
                "LLM generation stopped after "
                f"{attempts} attempts with {available_programs}/{self.llm_program_num} "
                "valid programs. Try a lower temperature or a different model."
            )

    def _parse_response(self, response: str, mode: str):
        candidates: list[str] = []
        errors: list[str] = []
        extractors: list[tuple[str, Callable]] = []
        if mode in {"python_to_dsl", "python"}:
            extractors.append(("python", get_program_str_from_llm_response_python))
        if mode in {"python_to_dsl", "dsl"}:
            extractors.append(("dsl", get_program_str_from_llm_response_dsl))

        for name, extractor in extractors:
            try:
                candidates.append(extractor(response, env_name=self.env_name))
            except Exception as error:
                errors.append(f"{name} extraction: {type(error).__name__}: {error}")

        parsed = []
        for candidate in candidates:
            try:
                parsed.append(self.dsl.parse_str_to_node(candidate))
            except Exception as error:
                errors.append(f"DSL parse: {type(error).__name__}: {error}")
        if not parsed:
            return None, errors or ["No program was found in the response."]
        if mode == "python_to_dsl":
            return self.np_rng.choice(parsed), errors
        return parsed[0], errors

    def _generate_programs(
        self,
        system_prompt: str,
        user_prompt: str,
        mode: str,
    ) -> tuple[list, dict]:
        programs = []
        record_list = []
        attempts = 0
        target = self.llm_program_num
        progress = tqdm(
            total=target,
            desc="Valid LLM programs",
            unit="program",
            dynamic_ncols=True,
            disable=not _progress_enabled(),
        )
        try:
            while len(programs) < target:
                self._check_generation_attempts(attempts, len(programs))
                attempts += 1
                seed = int(self.np_rng.randint(0, 2**32))
                planned = math.ceil((target - len(programs)) * self.ratio)
                attempt_responses: list[str] = []
                for batch, request_info in self._iter_llm_batches(
                    system_prompt,
                    user_prompt,
                    planned,
                    seed,
                    attempt=attempts,
                ):
                    attempt_responses.extend(batch)
                    parse_results = []
                    for response_index, response in enumerate(batch, 1):
                        program, errors = self._parse_response(response, mode)
                        if program is None:
                            reason = "; ".join(errors)[:600]
                            print(
                                f"LLM candidate rejected: attempt {attempts}, "
                                f"batch {request_info['batch_number']}, response "
                                f"{response_index}: {reason}",
                                flush=True,
                            )
                            self._emit(
                                "candidate_rejected",
                                attempt=attempts,
                                batch_number=request_info["batch_number"],
                                response_index=response_index,
                                reason=reason,
                            )
                            parse_results.append({"valid": False, "reason": reason})
                            continue

                        programs.append(program)
                        progress.update(1)
                        self._emit(
                            "candidate_generated",
                            program=program,
                            candidate_index=len(programs),
                            target=target,
                            dsl=self.dsl,
                        )
                        dsl_program = self.dsl.parse_node_to_str(program)
                        parse_results.append({"valid": True, "dsl_program": dsl_program})
                        print(
                            f"LLM candidate accepted: {len(programs)}/{target}",
                            flush=True,
                        )
                        if len(programs) >= target:
                            break

                    self._write_debug(
                        **request_info,
                        status="completed",
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        responses=batch,
                        parse_results=parse_results,
                        valid_programs=len(programs),
                        target_programs=target,
                    )
                    if len(programs) >= target:
                        remaining_batches = (
                            request_info["total_batches"] - request_info["batch_number"]
                        )
                        if remaining_batches:
                            print(
                                "Valid-program target reached; skipping "
                                f"{remaining_batches} remaining LLM request(s).",
                                flush=True,
                            )
                        break

                print(
                    f"Attempts: {attempts}, Program_nums: {len(programs)}",
                    flush=True,
                )
                record_list.append(
                    {
                        "seed": seed,
                        "temperature": self.temperature,
                        "top_p": self.top_p,
                        "system_prompt": system_prompt,
                        "user_prompt": user_prompt,
                        "llm_response": attempt_responses,
                        "available_program_num": len(programs),
                        "program_str_list": [
                            self.dsl.parse_node_to_str(program) for program in programs
                        ],
                    }
                )
        finally:
            progress.close()

        log = {"attemps": attempts, "attempts": attempts, "record_list": record_list}
        return programs[:target], log

    def get_program_list_python_to_dsl(self) -> tuple[list, dict]:
        return self._generate_programs(
            self.prompt_generator.get_system_prompt_python_to_dsl(),
            self.prompt_generator.get_user_prompt_python_to_dsl(),
            "python_to_dsl",
        )

    def get_program_list_python(self) -> tuple[list, dict]:
        return self._generate_programs(
            self.prompt_generator.get_system_prompt_python(),
            self.prompt_generator.get_user_prompt_python(),
            "python",
        )

    def get_program_list_dsl(self) -> tuple[list, dict]:
        return self._generate_programs(
            self.prompt_generator.get_system_prompt_dsl(),
            self.prompt_generator.get_user_prompt_dsl(),
            "dsl",
        )

    def get_program_list_revision_regeneration_with_reward(self, progs_rewards):
        return self._generate_programs(
            self.prompt_generator.get_system_prompt_python_to_dsl(),
            self.prompt_generator.get_user_prompt_revision_regeneration_with_reward(
                progs_rewards, self.dsl
            ),
            "python_to_dsl",
        )

    def get_program_list_revision_regeneration(
        self, previous_program_list: List[dsl_nodes.Program]
    ):
        return self._generate_programs(
            self.prompt_generator.get_system_prompt_python_to_dsl(),
            self.prompt_generator.get_user_prompt_revision_regeneration(
                previous_program_list, self.dsl
            ),
            "python_to_dsl",
        )

    def get_program_list_revision_agent_execution_trace(
        self,
        reward: float,
        logs: list[dict[str, str]],
        average_reward: float,
    ) -> tuple[list[dsl_nodes.Program], dict]:
        return self._generate_programs(
            self.prompt_generator.get_system_prompt_python_to_dsl(),
            self.prompt_generator.get_user_prompt_revision_agent_execution_trace(
                reward, logs, average_reward
            ),
            "python_to_dsl",
        )

    def get_program_list_revision_agent_program_execution_trace(
        self,
        reward: float,
        logs: list[dict[str, str]],
        average_reward: float,
    ) -> tuple[list[dsl_nodes.Program], dict]:
        return self._generate_programs(
            self.prompt_generator.get_system_prompt_python_to_dsl(),
            self.prompt_generator.get_user_prompt_revision_agent_program_execution_trace(
                reward, logs, average_reward
            ),
            "python_to_dsl",
        )
