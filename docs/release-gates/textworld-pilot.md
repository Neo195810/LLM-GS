# TextWorld pilot formal-benchmark release gate

`TextWorldPilot` is an additive V2 pilot, not an initial-benchmark replacement.
Karel and MiniGrid retain the four initial benchmark tasks. Craftax remains the
long-horizon/throughput alternative and HighwayEnv remains the continuous-state
safety-control alternative; neither is an automatic fallback.

The pilot accepts only the `textworld-pilot-dsl-v1` rules implemented by
`llm_gs.textworld_pilot`. Its frozen quest vocabulary is `key` and `chest`;
its predicates are `not_has_key`, `has_key`, `chest_unlocked`, and
`chest_open`; and its actions compile only to `take key`, `unlock chest with
key`, and `open chest`. The adapter records facts, canonical commands, explicit
win facts, and explicit fail facts.

Promotion to a formal benchmark is blocked unless the persisted JSON evidence is
accepted by `llm-gs textworld promote --evidence <path>` (which calls
`evaluate_release_gate`). An ordinary `llm-gs run` remains a pilot execution
and never creates a formal-benchmark claim. The artifact must contain all of
the following:

1. A clean Python 3.11 installation.
2. A recorded TextWorld and transitive-license review.
3. Exactly 100 seeds replayed in two independent processes with zero mismatches.
4. Structured evidence for success, invalid action, unsatisfied precondition,
   timeout, and runtime error (or an explicit not-applicable record).
5. Measured single/batch p95 wall time, peak memory, and p95 trace bytes on the
   V2 target machine.

The release-gate code deliberately does not infer any of these results from a
unit test or from a package declaration. Until recorded measurements and review
evidence are supplied, the pilot cannot be represented as a formal benchmark.

## Promotion status

`llm-gs textworld promote --evidence docs/release-gates/textworld-release-evidence.json`
passed on 2026-08-14 under a clean `.venv` (Python 3.11.15). The evidence
artifact was produced by `scripts/generate_textworld_release_evidence.py`,
which replays 100 seeds across two independent `.venv` Python processes,
exercises real success/invalid-action/unsatisfied-precondition episodes,
records timeout and runtime-error as not-applicable with code citations, and
measures single- and batch-episode p95 latency, peak RSS, and p95 trace
bytes in a fresh process. The transitive-license review is recorded in
`NOTICE`.
