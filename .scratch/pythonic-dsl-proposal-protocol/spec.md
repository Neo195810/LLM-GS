# Pythonic-DSL Proposal Protocol

**Status:** ready-for-agent

## Problem Statement

Karel and MiniGrid proposals currently ask the model to write an artificial delimiter DSL
directly. Structured output constrains the outer JSON object but not the nested DSL syntax,
so delimiter mistakes, empty source, and repeated invalid output can exhaust bounded correction
without creating a Candidate Program.

## Solution

New Karel and MiniGrid executions use the versioned `pythonic-dsl-v1` Proposal Protocol. The
model returns a restricted Python program and a DSL backup. The system first validates and
deterministically lowers Python to canonical DSL; only when that fails does it conservatively
normalize and validate the backup. If neither path admits a Candidate Program, the existing two
self-contained corrections and Model Output Failure boundary remain in effect.

## User Stories

1. As a program-synthesis researcher, I want Karel and MiniGrid proposals written in restricted Python, so that delimiter syntax does not waste Model Budget.
2. As a Proposer, I want accepted Python deterministically lowered to canonical DSL, so that current evaluators remain usable.
3. As a researcher, I want a DSL backup in every response, so that a Python parsing error need not discard a usable policy.
4. As a maintainer, I want Python admission to take precedence over backup admission, so that every Candidate Program has an unambiguous primary path.
5. As a maintainer, I want only semantics-preserving DSL normalization, so that fallback cannot silently alter policy control flow.
6. As a Proposer, I want Correction Feedback to include bounded Python and backup diagnostics, so that correction addresses the actual admission failure.
7. As a researcher, I want the accepted admission path counted, so that fallback usage is measurable without exposing raw model output.
8. As an auditor, I want raw failed proposal pairs retained only as private Invalid-output Artifacts, so that evidence remains redacted and bounded.
9. As an experiment runner, I want the new protocol recorded in the Experiment Manifest, so that it has a distinct Experiment ID from direct-DSL results.
10. As a maintainer, I want historical direct-DSL workspaces and bundles to remain readable, so that prior evidence is not rewritten.
11. As a TextWorldPilot user, I want its existing source contract unchanged, so that this intervention stays limited to Karel and MiniGrid.
12. As a test author, I want translator, normalizer, correction, and reporting tested at existing seams, so that no new live ablation is required.

## Implementation Decisions

- Karel tasks (CleanHouse and FourCorners) and MiniGrid tasks (DoorKey and RedBlueDoor) use
  structured-output v3 with required non-empty `python_source` and `dsl_backup`, each limited to
  2,000 characters. TextWorldPilot and OfflineEcho retain their current source contract.
- A task-aware proposal-contract resolver replaces one global proposal-schema identity. New
  manifests record `pythonic-dsl-v1`, the translator and normalizer versions, the schema version,
  and the Pythonic prompt hash.
- The allowed Python subset is exactly one zero-argument `def run():` containing allowlisted
  action calls, `if` with optional `else`, predicate-guarded `while`, and
  `for _ in range(<integer 0..19>)`. Imports, declarations, variables, assignment, arbitrary
  calls, attribute access, keyword arguments, `elif`, boolean literals, `and`, `or`, exceptions,
  comprehensions, and every other AST form are rejected.
- The translator maps task-allowlisted actions and predicates to the existing DSL. It lowers
  `if`, `if/else`, `while`, and bounded `for` to IF/IFELSE, WHILE, and REPEAT, renders canonical
  DSL, then re-parses with the existing local parser before Candidate Program admission.
- The Conservative Normalizer may remove code fences, normalize known-token whitespace, remove
  `()` from allowlisted zero-argument actions, and append exactly one missing top-level `m)` only
  when that addition yields a valid parse. It must reject inferred nested delimiters, guessed
  duplicate tokens, control-flow rewriting, and `while True` to fixed-repeat conversion.
- Python admission is preferred. If it fails, the normalized backup may be admitted; if both fail,
  the current bounded correction process continues. Request limits, correction count, retry
  policy, Model Budget, cost accounting, and Model Output Failure classification do not change.
- Correction Feedback includes bounded, redacted previous Python, DSL backup, and each admission
  diagnostic. Repetition detection fingerprints the normalized complete proposal pair.
- An admission observer records only `python`, `backup`, or `normalized-backup` path metadata and
  failure summaries in the private execution audit. Successful raw model outputs remain unretained.
- Public reports and exports expose aggregate admission-path counts only. Raw Python, backup DSL,
  and correction prompts never cross the private evidence boundary.
- No SQLite migration, historical workspace rewrite, bundle rewrite, or specification toggle is
  introduced. Historical records have no admission-path aggregate.

## Testing Decisions

- Test proposal admission end to end: structured response pair to Candidate Program, correction,
  or Model Output Failure.
- Cover valid Python lowering for every Karel and MiniGrid task, and assert rendered DSL passes the
  existing parser and evaluator compatibility tests.
- Reject every disallowed Python AST category, task-invalid action or predicate, illegal range,
  malformed function, and empty body.
- Test every accepted normalizer rule and verify ambiguous delimiter repair, control-flow change,
  and `while True` rewriting are rejected.
- Test Python precedence, backup admission, normalized-backup admission, dual failure, repeated
  output, redaction, report aggregation, export safety, and legacy workspace/bundle reads.
- Use existing proposer, execution, storage, Matrix Report, and adapter-equivalence seams. Run the
  full automated suite; do not run a new live or direct-versus-Pythonic ablation.

## Out of Scope

- New ablation experiments or re-running published direct-DSL studies.
- Pythonic-DSL for TextWorldPilot or OfflineEcho.
- Semantic guessing or arbitrary repair of malformed DSL.
- Changes to correction limits, provider retry policy, Model Budget, evaluation budget, or cost policy.
- Migration or rewriting of historical workspaces, Matrix Reports, or export bundles.
- Publishing raw proposal material.

## Further Notes

- The new decision supersedes ADR-0016 only for new Karel and MiniGrid executions; direct-DSL
  artifacts remain historically valid.
- Implementation adds ADR-0036 and the glossary terms Pythonic Proposal, Backup DSL, Proposal
  Admission Path, and Conservative Normalizer.
