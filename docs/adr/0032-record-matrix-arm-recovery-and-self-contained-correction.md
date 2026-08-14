# Record matrix-arm recovery and self-contained correction

Each preregistered Matrix Arm owns a durable lifecycle and retains immutable Execution history. Completed arms alone enter protocol-specific statistics; model-output, infrastructure, and budget failures stay explicit in missingness and failure accounting. Correction and repair requests are self-contained with bounded structured feedback rather than implicit OpenAI conversation state, so they remain auditable and reproducible while preserving the prior failed output and relevant evidence needed for repair.

## Consequences

Infrastructure operations make at most two recorded retries before an Execution becomes infrastructure-failed; later recovery creates a new Execution. Exhausted format correction becomes model-output-failed, and exhausted total cost becomes blocked-by-budget. Invalid-output artifacts are bounded and redacted before private retention; program logic is never automatically inferred or rewritten.

## Invalid-output artifact policy

Every schema- or DSL-invalid response is retained as an Invalid-output Artifact before its correction request is made, including invalid responses from initial proposal and repair. A later successful correction does not remove earlier invalid artifacts. Successful raw model outputs are not retained.

Artifacts are associated with their Execution, phase, and correction-attempt number, including failures before a Candidate Program exists. They retain redacted response and correction-prompt material, parser/schema/DSL validation stage and exact error, finish reason, token usage, and artifact hashes. Empty provider responses still produce an artifact with their available metadata.

Artifacts stay private in the durable workspace for its lifetime. Matrix reports and export bundles expose only counts, error kinds, and redacted artifact hashes, never raw text. Redaction occurs before capping, hashing, and content-addressed storage; it removes configured API keys, environment values named `KEY`, `TOKEN`, `SECRET`, `PASSWORD`, or `CREDENTIAL`, and recognized secret patterns. Each response and correction prompt is capped at 64 KiB with original length and truncation metadata.

Failure to persist a required Invalid-output Artifact is an infrastructure failure. This preserves the guarantee that model-output failures have diagnostic evidence.
