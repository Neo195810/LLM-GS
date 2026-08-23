from __future__ import annotations

import argparse
import json
import pathlib
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from prog_policies.skill_gs.llm_repair import repair_doorkey_llm_policy


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repair one failed LLM-generated DoorKey policy result."
    )
    parser.add_argument("--input", required=True, help="Path to an LLM smoke result JSON.")
    parser.add_argument("--output", required=True, help="Path for the repair result JSON.")
    parser.add_argument(
        "--skill-store",
        help="Optional JSON skill database path for the learned repair skill.",
    )
    parser.add_argument("--source-label", default="unknown")
    args = parser.parse_args()

    input_path = pathlib.Path(args.input)
    output_path = pathlib.Path(args.output)
    llm_result = json.loads(input_path.read_text(encoding="utf-8"))
    result = repair_doorkey_llm_policy(
        llm_result,
        skill_store_path=args.skill_store,
        source_label=args.source_label,
    )

    payload = json.dumps(result, indent=2)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
