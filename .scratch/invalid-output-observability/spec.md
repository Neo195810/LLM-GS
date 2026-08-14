# Invalid-output observability

Status: `ready-for-agent`

## Problem Statement

When a Proposer or Reflector/Repairer exhausts bounded schema and DSL correction, LLM-GS records a Model Output Failure but does not retain the invalid response, correction prompt, or validation evidence that would explain it. The live ablation matrix therefore reports two model-output failures without enough evidence to determine whether their cause was malformed model output, prompt design, or a parser mismatch. This blocks evidence-based decisions about future model spend.

## Solution

Retain a private, append-only Invalid-output Artifact for every invalid model response produced during initial proposal or repair. Record it before issuing a correction request and associate it with the Execution, phase, and correction-attempt number, including failures before a Candidate Program exists. Store bounded, redacted response and correction-prompt content as content-addressed artifacts, with structured validation and request metadata. Do not retain successful raw model outputs. Keep artifacts private to the durable workspace; reports and export bundles expose only safe metadata and redacted hashes.

## User Stories

1. As an experiment operator, I want each invalid initial proposal preserved, so that I can diagnose a terminal Model Output Failure.
2. As an experiment operator, I want each invalid repair response preserved, so that I can distinguish proposal and repair failures.
3. As an experiment operator, I want every correction attempt linked to its Execution and phase, so that I can reconstruct the bounded correction sequence.
4. As an experiment operator, I want invalid attempts preserved even when a later correction succeeds, so that I can measure correction cost and prompt quality.
5. As an experiment operator, I want parser, schema, and DSL validation stage and error retained, so that I can identify the failed contract.
6. As an experiment operator, I want finish reason and token-usage metadata retained, so that I can identify truncation or provider-side behavior.
7. As an experiment operator, I want artifacts for empty provider responses, so that absence of output remains auditable.
8. As a security-conscious operator, I want known secrets and recognized secret patterns redacted before storage, hashing, or export, so that diagnostic retention does not preserve credentials.
9. As a security-conscious operator, I want bounded artifact content with original-size and truncation metadata, so that observability has predictable storage cost.
10. As an analyst, I want matrix reports to expose safe counts, error kinds, and artifact hashes only, so that reports remain shareable without raw model text.
11. As an export consumer, I want export bundles to omit raw Invalid-output Artifact content, so that private workspace evidence cannot leak through a bundle.
12. As an operator, I want failed diagnostic persistence treated as infrastructure failure, so that a Model Output Failure always carries its promised evidence.
13. As a maintainer, I want existing Model Output Failure classification unchanged when artifact persistence succeeds, so that matrix statistics remain comparable.
14. As a maintainer, I want artifacts retained for the durable workspace lifetime, so that a completed live run remains diagnosable.

## Implementation Decisions

- Introduce a model-output observer seam between proposal/repair validation and the Attempt Store. The Proposer emits invalid-output observations; execution supplies its already-created identity; storage owns persistence.
- Persist one append-only observation for every invalid model response before its next correction request. Include execution identity, phase (`initial` or `repair`), correction-attempt number, validation stage, exact validation error, finish reason, token usage, response artifact hash, correction-prompt artifact hash, original lengths, and truncation flags.
- Redact before applying the 64 KiB per-field bound, hashing, or content-addressed persistence. Redaction covers configured API keys, environment values whose names contain `KEY`, `TOKEN`, `SECRET`, `PASSWORD`, or `CREDENTIAL`, and recognized secret patterns.
- Store artifacts only in the private durable workspace. Do not persist successful raw outputs.
- Persist empty-response observations when validation fails, using available metadata.
- Require artifact persistence for a Model Output Failure. If it cannot be persisted, surface an infrastructure failure instead.
- Reports and export bundles retain metadata and redacted artifact hashes, but omit raw invalid-output content.
- Preserve existing Model Output Failure and matrix failure-class semantics when observation persistence succeeds.

## Testing Decisions

- Test externally visible behavior at the highest seam: matrix or CLI execution records diagnosable invalid-output attempts and preserves Model Output Failure classification.
- Add focused proposal/repair validation-loop tests for each invalid response, correction prompt, eventual success after invalid output, terminal exhaustion, and empty response.
- Add Attempt Store tests for append-only records, execution/phase/attempt association, content-addressed references, 64 KiB truncation metadata, and redaction-before-hash behavior.
- Add export and report tests proving raw invalid-output text never appears while safe metadata and hashes do.
- Add failure-path tests proving observation-persistence failure becomes infrastructure failure.
- Follow existing proposer, matrix, storage, and offline tracer-bullet test conventions for deterministic fake responses and durable-store assertions.

## Out of Scope

- Retaining successful raw model responses.
- Publishing raw invalid-output content in reports, export bundles, or external issue trackers.
- Automatically changing prompts, parser rules, DSL rules, or Candidate Programs based on retained evidence.
- Changing correction limits, model selection, cost budgets, or matrix success metrics.
- Encrypting workspace artifacts at rest or introducing a remote observability service.

## Further Notes

This specification uses the domain terms Invalid-output Artifact, Execution, Model Output Failure, Correction Feedback, and Attempt Store as defined in `CONTEXT.md`. It implements the private, bounded, redacted retention policy recorded in ADR 0032.
