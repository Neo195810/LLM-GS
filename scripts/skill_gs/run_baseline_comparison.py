from __future__ import annotations

import argparse
import json
import pathlib
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from prog_policies.skill_gs import run_doorkey_baseline_comparison


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run fair DoorKey baseline comparison for Skill-GS."
    )
    parser.add_argument("--seeds", type=int, nargs="*")
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--seed-end", type=int, default=127)
    parser.add_argument("--initial-max-steps", type=int, default=10)
    parser.add_argument(
        "--search-candidate-max-steps",
        type=int,
        nargs="*",
        default=[10, 20, 22, 24],
    )
    parser.add_argument(
        "--ours-retry-budget-schedule",
        type=int,
        nargs="*",
        default=[20, 22, 24],
    )
    parser.add_argument("--ours-retry-max-steps", type=int)
    parser.add_argument("--ours-max-attempts", type=int)
    parser.add_argument("--perturbation-seed", type=int, default=123)
    parser.add_argument(
        "--replanner-policy",
        choices=["legacy", "attribution_aware"],
        default="attribution_aware",
    )
    parser.add_argument("--include-runs", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()

    seeds = (
        args.seeds
        if args.seeds
        else list(range(args.seed_start, args.seed_end + 1))
    )
    result = run_doorkey_baseline_comparison(
        seeds=seeds,
        initial_max_steps=args.initial_max_steps,
        search_candidate_max_steps=args.search_candidate_max_steps,
        ours_retry_budget_schedule=args.ours_retry_budget_schedule,
        ours_retry_max_steps=args.ours_retry_max_steps,
        ours_max_attempts=args.ours_max_attempts,
        perturbation_seed=args.perturbation_seed,
        replanner_policy=args.replanner_policy,
        include_runs=args.include_runs,
    )
    payload = json.dumps(result, indent=2)
    if args.output:
        output_path = pathlib.Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
