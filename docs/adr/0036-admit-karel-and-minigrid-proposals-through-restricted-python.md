# Admit Karel and MiniGrid proposals through restricted Python

New Karel and MiniGrid executions use the versioned `pythonic-dsl-v1` Proposal
Protocol. A Structured Output response contains bounded `python_source` and
`dsl_backup` fields. The runtime accepts only a restricted `def run():` Python
subset, lowers it deterministically to canonical task DSL, and validates that
DSL through the existing parser before creating a Candidate Program.

The Python subset permits allowlisted action calls, `if` with optional `else`,
predicate-guarded `while`, and `for _ in range(<integer 0..19>)`. All other
syntax, non-allowlisted task symbols, and invalid bounds are rejected. Ticket
01 intentionally does not admit the backup: a later protocol increment may
add conservative backup normalization without changing this primary path.

TextWorldPilot and OfflineEcho remain on their existing direct-DSL contract.
Historical direct-DSL Experiment Manifests remain readable. New Pythonic
Manifests record the proposal protocol, schema version, and translator version
so their Experiment IDs cannot collide with direct-DSL executions.

## Consequences

The proposal schema changes only for Karel and MiniGrid requests, preserving
the existing Model Budget and bounded correction count. Every admitted Pythonic
Candidate Program is still canonical DSL at the evaluator boundary, so existing
task evaluators and AST-based analysis remain applicable. A malformed Pythonic
response creates no Candidate Program and continues through the existing
Model Output Failure process.
