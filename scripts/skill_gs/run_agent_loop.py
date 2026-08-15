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
    args = parser.parse_args()

    seeds = args.seeds if args.seeds else [args.seed]
    result = run_doorkey_agent_loop(
        seeds=seeds,
        max_steps=args.max_steps,
        skill_store_path=args.skill_store,
        include_runs=args.include_runs,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
