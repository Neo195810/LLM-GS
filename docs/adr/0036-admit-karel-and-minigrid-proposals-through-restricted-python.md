# Admit Karel and MiniGrid proposals through restricted Python

New Karel and MiniGrid executions use the versioned `pythonic-dsl-v1` Proposal
Protocol. A Structured Output response contains bounded `python_source` and
`dsl_backup` fields. The runtime accepts only a restricted `def run():` Python
subset, lowers it deterministically to canonical task DSL, and validates that
DSL through the existing parser before creating a Candidate Program.

The Python subset permits allowlisted action calls, `if` with optional `else`,
predicate-guarded `while`, and `for _ in range(<integer 0..19>)`. All other
syntax, non-allowlisted task symbols, and invalid bounds are rejected. Python
admission always takes precedence. Only if it fails may the versioned
Conservative Normalizer remove unambiguous backup-DSL formatting before that
backup is validated through the same parser. It never infers control flow or
otherwise synthesizes a policy.

TextWorldPilot and OfflineEcho remain on their existing direct-DSL contract.
Historical direct-DSL Experiment Manifests remain readable. New Pythonic
Manifests record the proposal protocol, schema version, and translator version
so their Experiment IDs cannot collide with direct-DSL executions.

## Consequences

The proposal schema changes only for Karel and MiniGrid requests, preserving
the existing Model Budget and bounded correction count. Every admitted Pythonic
Candidate Program is still canonical DSL at the evaluator boundary, so existing
task evaluators and AST-based analysis remain applicable. A malformed pair
creates no Candidate Program and continues through the existing Model Output
Failure process. The private execution audit records only the admission path
and failed-pair diagnostics under its redaction boundary; public reports and
exports expose only aggregate path counts. This preserves historical
direct-DSL workspaces and bundles without fabricating provenance for them.
