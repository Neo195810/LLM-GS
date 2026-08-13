# 07 — Append-only Attempt Store and recovery

**What to build:** Replace the tracer-bullet persistence model with the recoverable V2 Attempt Store: immutable Program Attempts and Episode Evaluations, content-addressed Artifacts, migrated WAL-backed SQLite records, idempotent Work Units, and atomic accounting that resumes safely after interruption.

**Blocked by:** 06 — CleanHouse Reflect repair cycle.

**Status:** blocked

**Acceptance criteria:**

- [ ] Every Program Attempt, lineage edge, Evaluation Evidence, Execution Summary, and submitted model cost is append-only and scoped by Experiment and Execution identity.
- [ ] Large retained content is content-addressed, referenced by hash, and never automatically deletes referenced Artifacts.
- [ ] Interrupted running Work Units return safely to pending; completed evaluation and budget accounting commit atomically without duplication.
- [ ] Migration, WAL transaction, Artifact hash, idempotency, and crash-recovery behavior are integration-tested.
