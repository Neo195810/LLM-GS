from __future__ import annotations

import argparse
import json
import pathlib
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from prog_policies.skill_gs.evidence_pack import generate_evidence_pack


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Skill-GS demo charts and summary report."
    )
    parser.add_argument(
        "--baseline-json",
        default="output/skill_gs/baseline_comparison_seed0_127.json",
    )
    parser.add_argument(
        "--report",
        default="reports/skill_gs_demo_evidence_pack_2026-08-22.md",
    )
    parser.add_argument("--assets-dir", default="reports/assets")
    args = parser.parse_args()

    comparison_path = pathlib.Path(args.baseline_json)
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    result = generate_evidence_pack(
        comparison=comparison,
        report_path=args.report,
        assets_dir=args.assets_dir,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
