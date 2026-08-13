# 01 — V2 offline tracer bullet

**What to build:** Establish the V2 executable foundation: a Python 3.11 `uv` package, validated Experiment Specification resolving to an immutable Experiment Manifest and Experiment ID, a local SQLite workspace, and a deterministic fake-model offline experiment exposed through the CLI. This ticket is the local tracker’s historical anchor: V2 was planned on `nrnmnrn/LLM-GS-V2` branch `codex/v2-spec` as original #2–#18; the target is now `Neo195810/LLM-GS` branch `nrnmnrn/llm-gs-v2`; the source branch has been merged; and all Git-tracked V2 files were confirmed transferred with identical content.

**Blocked by:** None — historical first slice.

**Status:** completed / resolved

**Acceptance criteria:**

- [x] A fake OpenAI client can run one offline Candidate Program through the CLI and produce a deterministic report without credentials or API cost.
- [x] Strict YAML validation, fully resolved Manifest identity, and display-name-independent Experiment IDs are covered by automated tests.
- [x] The workspace persists the Manifest and report in SQLite and supports deterministic report retrieval.
- [x] `pyproject.toml` and `uv.lock` establish the Python 3.11 V2 runtime authority.

## Resolution record

Completed by the merged V2 tracer-bullet commit. It deliberately proves only the highest-level offline seam; it does not claim that V1 adapters, real Tasks, OpenAI integration, recovery, Experience Memory, or the full CLI are complete. The current implementation therefore remains the baseline for the tickets below. Existing V1-wide Ruff findings are unrelated historical debt and are explicitly excluded from ticket 02.
