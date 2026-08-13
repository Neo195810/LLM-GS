# 05 — CleanHouse Hill Climbing with Regenerate

**What to build:** Deliver an executable CleanHouse experiment in which Hill Climbing explores Candidate Programs with the Regenerate failure strategy, uses resolved Evaluation and Model Budgets, and remains reproducible through the CLI with a fake OpenAI client.

**Blocked by:** 03 — CleanHouse evaluation contract; 04 — OpenAI structured role boundary.

**Status:** blocked

**Acceptance criteria:**

- [ ] A validated Experiment Specification can execute CleanHouse Hill Climbing with Regenerate end to end through the CLI.
- [ ] Failed candidates return to Global Search without creating synthetic Repair Cycles.
- [ ] Candidate and Episode counts, model usage, Attempt Outcomes, and budget exhaustion are observable in the persisted result.
- [ ] The fake-client experiment is deterministic and covered in default CI.
