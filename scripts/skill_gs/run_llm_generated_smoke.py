from __future__ import annotations

import argparse
import json
import pathlib
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from prog_policies.skill_gs.llm_generated_baseline import (
    run_llm_generated_one_shot_smoke,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one real LLM-generated DoorKey smoke baseline."
    )
    parser.add_argument("--provider", default="Ollama", choices=["Ollama", "OpenAI"])
    parser.add_argument("--prompt-template", required=True)
    parser.add_argument("--model", default="qwen3.5:latest")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument(
        "--reasoning-effort",
        default=None,
        help="OpenAI reasoning effort, such as none or low.",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        help="Maximum output tokens for OpenAI Responses requests.",
    )
    parser.add_argument(
        "--num-gpu",
        type=int,
        help="Ollama runtime GPU layers. Use 0 to force CPU for this request.",
    )
    parser.add_argument(
        "--num-predict",
        type=int,
        help="Maximum generated tokens for Ollama requests.",
    )
    parser.add_argument(
        "--think",
        dest="think",
        action="store_true",
        help="Enable thinking output for supported Ollama models.",
    )
    parser.add_argument(
        "--disable-thinking",
        dest="think",
        action="store_false",
        help="Disable thinking output so response contains only final JSON.",
    )
    parser.set_defaults(think=False)
    parser.add_argument(
        "--cache-dir",
        default="output/skill_gs/llm_generated_baseline",
    )
    parser.add_argument(
        "--skill-store",
        help="Optional JSON skill database to inject into {{skills_context}}.",
    )
    parser.add_argument(
        "--raw-response-file",
        help="Use a saved raw LLM response instead of calling Ollama.",
    )
    parser.add_argument("--output")
    args = parser.parse_args()

    generate_response = None
    if args.raw_response_file:
        raw_response_path = pathlib.Path(args.raw_response_file)

        def generate_response(prompt: str, model_name: str, temperature: float) -> str:
            return raw_response_path.read_text(encoding="utf-8")

    result = run_llm_generated_one_shot_smoke(
        prompt_template_path=args.prompt_template,
        model_name=args.model,
        seed=args.seed,
        temperature=args.temperature,
        provider=args.provider,
        cache_dir=args.cache_dir,
        skill_store_path=args.skill_store,
        num_gpu=args.num_gpu,
        think=args.think,
        num_predict=args.num_predict,
        reasoning_effort=args.reasoning_effort,
        max_output_tokens=args.max_output_tokens,
        generate_response=generate_response,
    )
    payload = json.dumps(result, indent=2)
    if args.output:
        output_path = pathlib.Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
