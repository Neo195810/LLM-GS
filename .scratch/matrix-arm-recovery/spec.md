# Make ablation-matrix recovery observable and self-correcting

## Problem statement

Live matrix runs can leave Matrix Arms unreported when proposal, parser,
evaluation, infrastructure, or budget failures occur. Model retries also lack
enough bounded feedback to correct invalid source reliably.

## Solution

Give every preregistered Matrix Arm a durable lifecycle and immutable Execution
history. Record one of `pending`, `running`, `completed`,
`model-output-failed`, `infrastructure-failed`, or `blocked-by-budget`, with a
bounded diagnostic record. Later recovery creates a new Execution rather than
mutating prior history.

LLM correction and repair requests are independent, self-contained requests.
They receive the Candidate Program, structured validation or evaluation
feedback, and the task's DSL contract. Preserve the contract and error details
when deterministically trimming context. Only extract permitted source/code
fences and normalize whitespace; never infer program logic.

## Decisions

- A model-output failure is terminal for its Execution; infrastructure and
  budget conditions are recoverable in a later Execution.
- Proposal and repair validation receive at most two correction requests after
  the initial invalid output.
- Each infrastructure operation receives at most two recorded retries before
  terminal infrastructure failure.
- Completed means the Execution reached an experiment result, not that its
  Candidate Program succeeded.
- Only completed arms enter protocol-specific Frozen or Online success rates
  and confidence intervals. All other states stay explicit in failure and
  missingness accounting.
- Invalid output is retained only as a bounded, redacted private artifact.

## Verification

Exercise the user-facing matrix run and report CLI with fake Responses and
evaluator clients. Cover each terminal state, immutable recovery, bounded
correction feedback, redaction/trimming, and Frozen/Online separation. Run the
focused tests, full pytest suite, mypy, and Ruff before live spending.

## Related decision

`docs/adr/0032-record-matrix-arm-recovery-and-self-contained-correction.md`
