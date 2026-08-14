# 04 — OpenAI structured role boundary

**What to build:** Enable the pinned OpenAI-only Proposer boundary for V2, with versioned proposal contracts and prompts, local DSL validation, explicit request parameters and usage accounting, bounded format correction, secret redaction, and a fake-client contract seam for default CI.

**Blocked by:** 03 — CleanHouse evaluation contract.

**Status:** done

**Acceptance criteria:**

- [x] Proposal requests use the pinned model and resolved prompt/parser identities, while fake payloads exercise the same contract without network access. Verified: `src/llm_gs/proposer.py:16-28` (`MODEL_NAME`, `PROPOSAL_SCHEMA`), `src/llm_gs/execution.py:65-90` (`FakeOpenAIClient`), `tests/test_openai_proposer.py:49-70`.
- [x] Schema-invalid, DSL-invalid, and output-length responses consume Model Budget and use at most two format-correction requests. Verified: `src/llm_gs/proposer.py:29` (`CORRECTION_ATTEMPTS = 2`), `src/llm_gs/proposer.py:142-177`, `tests/test_openai_proposer.py:73-88`.
- [x] Exhausted correction becomes Model Output Failure rather than a Program Attempt. Verified: `src/llm_gs/proposer.py:52-53,171-174` (`ModelOutputFailure`), `tests/test_openai_proposer.py:139-153`.
- [x] Request counts, input/output usage, finish information, and retry classification are recorded without retaining secrets. Verified: `src/llm_gs/proposer.py:81-88` (`ModelRequestRecord`), `src/llm_gs/proposer.py:378-393` (`_redact_secrets`), `tests/test_openai_proposer.py:91-116,169-192`.
