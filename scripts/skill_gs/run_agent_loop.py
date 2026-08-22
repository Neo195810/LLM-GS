from __future__ import annotations

import argparse
import json
import pathlib
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from prog_policies.skill_gs import run_doorkey_agent_loop


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Skill-GS agent workflow.")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--seeds", type=int, nargs="*")
    parser.add_argument("--max-steps", type=int, default=200)
    parser.add_argument("--skill-store")
    parser.add_argument("--include-runs", action="store_true")
    parser.add_argument("--adaptive-retry", action="store_true")
    parser.add_argument("--initial-max-steps", type=int)
    parser.add_argument("--retry-max-steps", type=int)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--attempt-memory")
    parser.add_argument("--perturbation-seed", type=int, default=0)
    parser.add_argument("--disable-perturbation", action="store_true")
    parser.add_argument(
        "--replanner-policy",
        choices=["legacy", "attribution_aware"],
        default="legacy",
    )
    args = parser.parse_args()

    seeds = args.seeds if args.seeds else [args.seed]
    result = run_doorkey_agent_loop(
        seeds=seeds,
        max_steps=args.max_steps,
        skill_store_path=args.skill_store,
        include_runs=args.include_runs,
        adaptive_retry=args.adaptive_retry,
        initial_max_steps=args.initial_max_steps,
        retry_max_steps=args.retry_max_steps,
        max_attempts=args.max_attempts,
        attempt_memory_path=args.attempt_memory,
        perturbation_seed=args.perturbation_seed,
        perturbation_enabled=not args.disable_perturbation,
        replanner_policy=args.replanner_policy,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
