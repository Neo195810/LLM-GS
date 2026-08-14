"""Child process worker: evaluate the TextWorld pilot for one seed and print JSON.

Run in a fresh Python process (never imported into the orchestrator's own
process) so replay artifacts come from genuinely independent processes, as
the release gate requires.
"""

from __future__ import annotations

import json
import sys

from llm_gs.contracts import CandidateProgram
from llm_gs.manifest import sha256_bytes
from llm_gs.textworld_pilot import TextWorldPilotAdapter, TextWorldPilotLimits

_SUCCESS_SOURCE = (
    "WHEN not_has_key DO take_key; WHEN has_key DO unlock_chest; "
    "WHEN chest_unlocked DO open_chest"
)


def main() -> None:
    seed = int(sys.argv[1])
    process_id = sys.argv[2]
    source = sys.argv[3] if len(sys.argv) > 3 else _SUCCESS_SOURCE
    adapter = TextWorldPilotAdapter()
    candidate = CandidateProgram(source=source)
    result = adapter.evaluate(candidate, seed=seed, limits=TextWorldPilotLimits(max_actions=3))
    terminal_state = result.terminal_state or ""
    print(
        json.dumps(
            {
                "seed": seed,
                "process_id": process_id,
                "terminal_state": terminal_state,
                "evidence_sha256": sha256_bytes(terminal_state.encode("utf-8")),
                "score": float(result.evaluation_evidence["score"]),
                "action_count": len(result.evaluation_evidence["commands"]),
                "outcome": result.outcome,
                "failure_reason": result.failure_reason,
            }
        )
    )


if __name__ == "__main__":
    main()
