from __future__ import annotations

import argparse
import glob
import json
import pathlib
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from prog_policies.skill_gs.llm_repair import repair_doorkey_llm_policy


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repair failed LLM-generated DoorKey policy result files."
    )
    parser.add_argument("--input-glob", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--skill-store", required=True)
    parser.add_argument("--summary-output")
    parser.add_argument("--source-label", default="unknown")
    args = parser.parse_args()

    input_paths = [pathlib.Path(path) for path in sorted(glob.glob(args.input_glob))]
    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    repaired_count = 0
    skipped_successful_count = 0
    successful_repairs = 0
    failed_repairs = 0

    for input_path in input_paths:
        llm_result = json.loads(input_path.read_text(encoding="utf-8"))
        seed = int(llm_result["seed"])
        evaluation = llm_result.get("evaluation", {})
        if evaluation.get("success"):
            skipped_successful_count += 1
            results.append(
                {
                    "seed": seed,
                    "input_path": str(input_path),
                    "status": "skipped_successful",
                    "output_path": "",
                    "success": True,
                }
            )
            continue

        output_path = output_dir / f"{input_path.stem}_repair.json"
        try:
            repair_result = repair_doorkey_llm_policy(
                llm_result,
                skill_store_path=args.skill_store,
                source_label=args.source_label,
            )
        except Exception as exc:
            failed_repairs += 1
            results.append(
                {
                    "seed": seed,
                    "input_path": str(input_path),
                    "status": "repair_failed",
                    "output_path": "",
                    "success": False,
                    "error": str(exc),
                }
            )
            continue

        output_path.write_text(json.dumps(repair_result, indent=2), encoding="utf-8")
        repaired_count += 1
        repair_success = bool(repair_result["repaired_evaluation"].get("success"))
        successful_repairs += int(repair_success)
        failed_repairs += int(not repair_success)
        results.append(
            {
                "seed": seed,
                "input_path": str(input_path),
                "status": "repaired",
                "strategy_id": repair_result["repair_plan"]["strategy_id"],
                "target_subgoal": repair_result["repair_plan"]["target_subgoal"],
                "output_path": str(output_path),
                "success": repair_success,
                "reward": repair_result["repaired_evaluation"].get("reward"),
                "steps": repair_result["repaired_evaluation"].get("steps"),
                "skill_memory": repair_result.get("skill_memory", {}),
            }
        )

    summary = {
        "source_label": args.source_label,
        "input_glob": args.input_glob,
        "input_count": len(input_paths),
        "repaired_count": repaired_count,
        "skipped_successful_count": skipped_successful_count,
        "successful_repairs": successful_repairs,
        "failed_repairs": failed_repairs,
        "skill_store_path": args.skill_store,
        "results": results,
    }
    payload = json.dumps(summary, indent=2)
    if args.summary_output:
        summary_path = pathlib.Path(args.summary_output)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
