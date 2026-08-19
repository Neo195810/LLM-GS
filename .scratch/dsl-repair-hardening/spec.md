# Harden DSL Correction Feedback and Model Output Recovery

Triage: `ready-for-agent`

## Problem Statement

Experiment operators are receiving too many Model Output Failures before a Candidate Program can be evaluated. In the analyzed 4096-token matrix run, 109 invalid outputs were retained: 99 responses completed but failed DSL validation, while 10 responses ended incomplete at the configured output-token limit. Most parser failures were recorded only as `Invalid program`, so Correction Feedback did not identify the failing construct, expected symbol, or actual symbol. When a model repeated an invalid response, the next self-contained correction request could be byte-identical to the previous one, encouraging the deterministic model to repeat the same invalid Candidate Program again.

The current diagnostics also reduce auditability: the generic secret redactor interprets `Unrecognized token: X` as credential-shaped text and replaces the DSL symbol with `[REDACTED]`. Separately, the MiniGrid Task contract reverses the value domains of object type and object color. These issues waste Model Budget, obscure Invalid-output Artifact evidence, and prevent Matrix Arms from reaching Program Attempt evaluation.

The 4096-token output limit is not the primary failure. Only 9.2% of retained invalid outputs were incomplete, while 90.8% were completed but syntactically invalid. Valid Program Attempts had a median source length of 258 characters and a 90th percentile of 529 characters. The configured limit should therefore remain fixed while the correction and validation paths are hardened.

## Solution

Make DSL validation failures actionable and make every bounded correction request capable of changing the result. Parser failures will identify the construct, local symbol position, expected symbol, actual symbol or end-of-input, and a bounded surrounding context. Correction Feedback will include the correction ordinal and will explicitly identify repeated invalid output, while remaining self-contained and bounded. The proposal contract will cap source length, give concise grammar-check instructions, handle incomplete provider responses explicitly, and correct the MiniGrid Task contract.

The existing two-correction bound and 4096-token output limit will remain unchanged. After implementation, a non-paid deterministic test suite and archived-output replay will verify the behavior. A separate small live pilot may measure the remaining incomplete rate; increasing the output limit is considered only if that rate remains above 2%, and any increase is a new Experiment Manifest and protocol rather than an in-place change.

## User Stories

1. As an experiment operator, I want a completed model response with invalid DSL to receive actionable Correction Feedback, so that a bounded correction can repair the actual syntax error.
2. As an experiment operator, I want repeated invalid output to produce a different correction request, so that Model Budget is not spent repeating a byte-identical request.
3. As an experiment operator, I want the correction request to state its ordinal, so that every self-contained request has deterministic recovery context.
4. As an experiment operator, I want an explicit repeated-output warning, so that the model knows it must not return the same Candidate Program unchanged.
5. As an experiment operator, I want incomplete responses distinguished from empty or malformed completed responses, so that the next correction asks for a shorter complete result.
6. As an experiment operator, I want the 4096-token output limit preserved initially, so that this repair does not silently change the preregistered Model Budget.
7. As a research engineer, I want the two-correction bound preserved, so that Matrix Arm budgets remain comparable with the intended experimental design.
8. As a research engineer, I want source length bounded independently of output-token capacity, so that a Candidate Program stays small enough to validate and evaluate reliably.
9. As a research engineer, I want proposal schema changes versioned, so that Experiment Manifests identify the exact model-output contract.
10. As a research engineer, I want changed Task prompts to produce changed prompt hashes and Experiment IDs, so that results from different protocols are not conflated.
11. As a Candidate Program authoring model, I want the first structural mismatch described with expected and actual DSL symbols, so that I can correct the failing construct before changing policy logic.
12. As a Candidate Program authoring model, I want concise delimiter checks and a valid nested-control example, so that I can verify unfamiliar DSL syntax before responding.
13. As a Candidate Program authoring model, I want correction requests to remain self-contained, so that correctness never depends on hidden API conversation state.
14. As a Candidate Program authoring model, I want the permitted source length stated in both schema and Correction Feedback, so that I can avoid an incomplete response.
15. As a MiniGrid Candidate Program authoring model, I want object-type and object-color value domains stated correctly, so that syntactically valid programs use semantically valid observations.
16. As a parser maintainer, I want malformed user input rejected by explicit exceptions rather than assertions, so that validation is active under every Python optimization mode.
17. As a parser maintainer, I want missing opening and closing delimiters reported separately, so that failures are diagnosable without reproducing the parser stack trace.
18. As a parser maintainer, I want invalid program wrappers, malformed `IFELSE` branches, and unexpected symbols to have consistent diagnostics, so that the proposer can present uniform feedback.
19. As an auditor, I want Invalid-output Artifacts to retain safe DSL symbols in validation evidence, so that failure causes remain inspectable.
20. As an auditor, I want credentials and secret-shaped values to remain redacted from responses, diagnostics, and correction prompts, so that improved observability does not weaken privacy.
21. As an auditor, I want existing Invalid-output Artifacts and Matrix Reports left immutable, so that historical evidence is not rewritten after the run.
22. As a platform maintainer, I want report and storage schemas left compatible, so that DSL hardening does not require a data migration.
23. As a platform maintainer, I want Model Output Failures to remain distinct from Program Attempts and policy outcomes, so that aggregate failure classification stays correct.
24. As a platform maintainer, I want a deterministic regression for repeated correction output, so that this production failure pattern cannot return unnoticed.
25. As an AFK implementation agent, I want acceptance criteria expressed at existing behavioral seams, so that I can implement the change without inventing a parallel test harness.
26. As a project owner, I want a small pilot criterion for revisiting the token limit, so that any later increase is evidence-based rather than speculative.

## Implementation Decisions

- Introduce an internal `DSLParseError` contract for Karel and MiniGrid validation. Its message and attributes identify the construct, local symbol offset, expected symbol, actual symbol or end-of-input, and a bounded token window.
- Replace parser assertions and generic `Invalid program` exceptions used for externally supplied source with explicit validation checks. Validation must behave identically with Python assertions enabled or disabled.
- Cover at least program wrappers, typed opening and closing delimiters, control headers, `IFELSE`/`ELSE` structure, repeat counts, MiniGrid feature delimiters, and unexpected symbols with the structured diagnostic contract.
- Preserve the existing Task-specific parser selection. TextWorldPilot keeps its fixed rule parser and existing vocabulary-specific errors.
- Keep Model Output Failure as the terminal classification when all bounded corrections remain schema-invalid or DSL-invalid. Invalid output still does not create a Program Attempt.
- Keep the correction allowance at two requests after the initial request. Do not increase Model Budget as part of this feature.
- Fingerprint each invalid response from its normalized extracted candidate content. Track fingerprints only within the current proposal or repair request.
- Add a one-based correction ordinal to every Correction Feedback request. When the current invalid fingerprint has already appeared, add a repeated-output warning that requires a structurally different complete replacement.
- Keep every correction request self-contained: include the protected Task contract, bounded latest candidate, actionable validation evidence, correction ordinal, and repeated-output status. Do not use previous response IDs or hidden conversation history.
- For DSL failures, instruct the model to repair the first reported structural mismatch before revising policy behavior. Never infer or automatically rewrite Candidate Program logic in the runtime.
- Recognize provider responses marked incomplete before generic schema extraction. Record a specific schema-stage error explaining that the configured output limit was reached and requesting complete JSON with a shorter, less deeply nested source.
- Upgrade the Structured Output proposal schema from `candidate_program_v1` to `candidate_program_v2` and add a 2,000-character maximum to `source`. Keep the source non-empty and keep additional properties forbidden.
- State the same 2,000-character source limit in initial Task prompts and Correction Feedback. The limit preserves 149 of the 150 valid Program Attempts observed in the analyzed run while excluding the extreme long-source case.
- Add a concise pre-return delimiter checklist and one parser-valid nested-control example to Karel and MiniGrid Task contracts. Avoid expanding prompts with a complete grammar tutorial.
- Correct the MiniGrid contract so `front_object_type` uses object values and `front_object_color` uses color values. Prompt examples must parse under the same local parser used for proposal validation.
- Change parser diagnostic wording so ordinary DSL symbols are not captured by the credential-oriented `token:` redaction pattern. Continue applying environment-value, API-key, bearer-token, password, credential, and recognized secret-pattern redaction before bounding and hashing.
- Do not alter the Invalid-output Artifact, Matrix Report, Attempt Store, or public CLI schemas. Existing content-addressed artifacts remain immutable and are not migrated.
- The proposal schema version, Task prompt hashes, source hash, Experiment Manifest, and Experiment ID will naturally change for subsequent runs. New results are a new protocol and must not overwrite or masquerade as the prior matrix run.
- Keep the output-token limit at 4096 for this implementation, consistent with the fixed-limit decision in ADR-0025. If a later pilot shows more than 2% incomplete responses after this hardening, evaluate 6144 tokens in a separately versioned manifest and cost envelope.
- The design continues to comply with ADR-0014 for executable DSL, ADR-0016 for versioned Structured Outputs, ADR-0025 for fixed calibrated token limits, and ADR-0032 for self-contained correction and private Invalid-output Artifacts.

## Testing Decisions

- Prefer the existing highest behavioral seam: drive `OpenAIProposer` with the sequential fake Responses client and assert returned Candidate Programs, bounded request count, correction-request contents, Invalid-output Artifact observations, and terminal Model Output Failure classification.
- Add a regression in which the fake client returns the same invalid Karel source repeatedly. The second correction prompt must differ from the first and must include both the new ordinal and repeated-output warning. A variant may return a valid third response only when it observes the warning, proving the complete recovery path.
- Add the missing incomplete-response fixture by returning provider status `incomplete` with 4096 output tokens and a partial JSON payload. Assert that the recorded validation stage remains schema, the diagnostic identifies the output limit, and the correction asks for a complete source within 2,000 characters.
- Extend existing Structured Output request-contract tests to assert the v2 schema name and `source.maxLength`, without asserting unrelated SDK call internals.
- Extend existing repair-prompt and Task-prompt contract tests to assert self-contained correction, delimiter checklist, nested parser-valid examples, source limit, and corrected MiniGrid feature domains.
- Test parser diagnostics directly only where exact parser behavior is the contract: missing opener, missing closer, malformed program wrapper, misplaced or absent `ELSE`, malformed MiniGrid feature delimiters, invalid repeat count, and unexpected symbol. Assert actionable fields or stable semantic fragments rather than complete incidental stack messages.
- Retain the existing task-specific rejection seam proving that a Karel-only action is rejected before DoorKey execution.
- Extend existing redaction behavior tests so a safe grammar symbol such as `w)` or `ELSE` remains present in validation evidence, while actual API keys, environment secrets, bearer credentials, passwords, and secret-shaped strings remain redacted.
- Retain the existing persistence and reporting seams to prove that invalid output is saved before correction, raw private content remains content-addressed, and reports or exports expose only safe metadata.
- Use minimized, anonymous examples derived from the observed production patterns rather than coupling automated tests to the local artifact directory. The patterns include missing typed openers, missing typed closers, malformed wrappers, misplaced `ELSE`, unexpected closing symbols, repeated invalid output, and incomplete JSON.
- As a non-gating diagnostic after implementation, replay archived invalid response artifacts through the new validator and require every parser-rejected Karel or MiniGrid response to produce an actionable diagnostic rather than a bare `Invalid program`. Do not rewrite those artifacts.
- Run the focused proposer, MiniGrid, TextWorldPilot, persistence, and report tests, followed by the complete pytest suite. The pre-existing proposer suite must remain green.
- Do not run a paid live matrix as part of automated acceptance. A later small pilot should measure completed-invalid rate, incomplete rate, repeated-output rate, Model Output Failure rate, and average token cost before any token-limit decision.

## Out of Scope

- Increasing the 4096-token output limit in the current protocol.
- Increasing the number of bounded correction attempts.
- Deterministically inserting, deleting, or rearranging DSL symbols to auto-repair Candidate Programs.
- Automatically changing Candidate Program policy logic based on parser or evaluation evidence.
- Redesigning Karel, MiniGrid, or TextWorldPilot DSL syntax.
- Changing policy evaluation limits, admission criteria, outcome classifiers, Search Strategies, Failure Handling Strategies, or Memory Protocols.
- Reclassifying Model Output Failures as Program Attempts or policy outcomes.
- Migrating or rewriting historical Invalid-output Artifacts, Attempt Store rows, Matrix Reports, or experiment bundles.
- Launching a paid live matrix run or changing the shared cost budget.
- Folding the later 6144-token experiment, if needed, into the same Experiment Manifest or Experiment ID.

## Further Notes

- Evidence from `my-third-run-live-4096`: 86 retained errors were bare `Invalid program`, 13 were redacted unexpected-token errors, and 10 were incomplete non-empty-source schema failures. Replaying private response artifacts showed that most failures were typed-delimiter placement or closure errors.
- A deterministic red-capable harness already demonstrates the retry defect: three identical invalid responses cause the two generated correction prompts to be byte-identical. Existing proposer tests pass, confirming a regression-test gap rather than a currently failing unit test.
- The agreed testing seam is the existing `OpenAIProposer` behavioral seam, with direct parser tests only for the structured diagnostic contract and existing persistence/report tests for privacy boundaries.
- The repository uses a local-file issue tracker. This specification is the `ready-for-agent` publication artifact; GitHub Issues must not be used.
- The unrelated working-tree modification to model pricing is not part of this feature and must be preserved untouched.
