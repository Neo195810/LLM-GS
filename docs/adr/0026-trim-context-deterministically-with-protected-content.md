# Trim context deterministically with protected content

Requests that reach their input limit use a versioned deterministic trimmer whose removals are fully recorded. System instructions, schemas, Task and DSL contracts, the current Candidate Program, and minimum failure evidence are protected; optional memory and evidence are removed in fixed priority order, and requests that still exceed the limit are blocked rather than silently summarized or submitted incomplete.
