from __future__ import annotations

import argparse
import json
import pathlib
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from prog_policies.skill_gs import run_doorkey_mvp, run_many_doorkey_mvp


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Skill-GS DoorKey MVP loop.")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--seeds", type=int, nargs="*")
    parser.add_argument("--max-steps", type=int, default=200)
    parser.add_argument("--trace-limit", type=int, default=40)
    parser.add_argument("--skill-store")
    args = parser.parse_args()

    if args.seeds:
        result = run_many_doorkey_mvp(
            args.seeds,
            max_steps=args.max_steps,
            skill_store_path=args.skill_store,
        )
        for run in result["runs"]:
            run["trace"] = run["trace"][: args.trace_limit]
    else:
        result = run_doorkey_mvp(
            seed=args.seed,
            max_steps=args.max_steps,
            skill_store_path=args.skill_store,
        )
        result["trace"] = result["trace"][: args.trace_limit]

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
