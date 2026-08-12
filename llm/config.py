from __future__ import annotations

import os

from llm.llm_program_generator import DEFAULT_OLLAMA_BASE_URL, DEFAULT_OLLAMA_MODEL


def add_llm_cli_arguments(parser) -> None:
    parser.add_argument(
        "--llm_provider",
        choices=("ollama", "openai"),
        default=os.getenv("LLM_PROVIDER", "ollama"),
    )
    parser.add_argument("--llm_model", default=os.getenv("LLM_MODEL"))
    parser.add_argument("--llm_base_url", default=os.getenv("LLM_BASE_URL"))
    parser.add_argument(
        "--llm_batch_size",
        type=int,
        default=int(os.getenv("LLM_BATCH_SIZE", "1")),
    )
    parser.add_argument(
        "--llm_max_attempts",
        type=int,
        default=int(os.getenv("LLM_MAX_ATTEMPTS", "3")),
    )
    parser.add_argument(
        "--llm_max_tokens",
        type=int,
        default=int(os.getenv("LLM_MAX_TOKENS", "1024")),
        help="Maximum output tokens per LLM request; 0 uses the provider default.",
    )
    parser.add_argument(
        "--llm_request_timeout",
        type=float,
        default=float(os.getenv("LLM_REQUEST_TIMEOUT", "300")),
        help="Timeout in seconds for one LLM request; 0 disables the timeout.",
    )


def llm_generator_kwargs(args, event_reporter=None) -> dict:
    options = {
        "llm_provider": args.llm_provider,
        "llm_model": args.llm_model,
        "llm_base_url": args.llm_base_url,
        "llm_batch_size": args.llm_batch_size,
        "llm_max_attempts": args.llm_max_attempts,
        "llm_max_tokens": args.llm_max_tokens,
        "llm_request_timeout": args.llm_request_timeout,
    }
    if event_reporter is not None:
        options["event_reporter"] = event_reporter
    return options


__all__ = [
    "DEFAULT_OLLAMA_BASE_URL",
    "DEFAULT_OLLAMA_MODEL",
    "add_llm_cli_arguments",
    "llm_generator_kwargs",
]
