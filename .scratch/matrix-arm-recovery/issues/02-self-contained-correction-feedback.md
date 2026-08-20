# 02 — Add self-contained correction feedback

**What to build:** When an LLM returns invalid structured output or task DSL, a
subsequent independent request receives bounded Correction Feedback: the prior
Candidate Program, error classification/message, task contract, and DSL
grammar/action allowlist. Repair requests receive bounded evaluation evidence.
The system may safely extract a source field or code fence and normalize
whitespace, but never guesses or rewrites program logic.

**Blocked by:** None — can start immediately.

**Status:** complete

- [x] Proposal and repair paths make at most two correction requests after the
  first invalid output, then record model-output failure.
- [x] Feedback preserves the relevant contract and is bounded with deterministic
  trimming and redaction.
- [x] Tests prove that retries are self-contained and do not use implicit API
  conversation linkage.

**Verified:** `uv run pytest tests/test_openai_proposer.py -q` (61 passed),
`uv run mypy src/llm_gs/proposer.py`, and focused Ruff checks.
