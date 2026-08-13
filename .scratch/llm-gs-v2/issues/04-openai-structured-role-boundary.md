# 04 — OpenAI structured role boundary

**What to build:** Enable the pinned OpenAI-only Proposer boundary for V2, with versioned proposal contracts and prompts, local DSL validation, explicit request parameters and usage accounting, bounded format correction, secret redaction, and a fake-client contract seam for default CI.

**Blocked by:** 03 — CleanHouse evaluation contract.

**Status:** blocked

**Acceptance criteria:**

- [ ] Proposal requests use the pinned model and resolved prompt/parser identities, while fake payloads exercise the same contract without network access.
- [ ] Schema-invalid, DSL-invalid, and output-length responses consume Model Budget and use at most two format-correction requests.
- [ ] Exhausted correction becomes Model Output Failure rather than a Program Attempt.
- [ ] Request counts, input/output usage, finish information, and retry classification are recorded without retaining secrets.
