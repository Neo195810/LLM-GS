# 07 — Append-only Attempt Store and recovery

**What to build:** Replace the tracer-bullet persistence model with the recoverable V2 Attempt Store: immutable Program Attempts and Episode Evaluations, content-addressed Artifacts, migrated WAL-backed SQLite records, idempotent Work Units, and atomic accounting that resumes safely after interruption.

**Blocked by:** 06 — CleanHouse Reflect repair cycle.

**Status:** done

**Acceptance criteria:**

- [x] Every Program Attempt, lineage edge, Evaluation Evidence, Execution Summary, and submitted model cost is append-only and scoped by Experiment and Execution identity. Verified: `src/llm_gs/storage.py:1001-1020` (append-only schema), `src/llm_gs/contracts.py:163` (`MemoryEntry` frozen), `tests/test_offline_tracer_bullet.py:37`.
- [x] Large retained content is content-addressed, referenced by hash, and never automatically deletes referenced Artifacts. Verified: `src/llm_gs/storage.py:989` (`_put_artifact`, sha256), `tests/test_offline_tracer_bullet.py:37`.
- [x] Interrupted running Work Units return safely to pending; completed evaluation and budget accounting commit atomically without duplication. Verified: `src/llm_gs/storage.py:27` (`PendingWork`), `src/llm_gs/storage.py:42` (recovery on init), `src/llm_gs/storage.py:212` (`complete_work`), `tests/test_offline_tracer_bullet.py:360`.
- [x] Migration, WAL transaction, Artifact hash, idempotency, and crash-recovery behavior are integration-tested. Verified: `src/llm_gs/storage.py:998` (WAL PRAGMA), `tests/test_offline_tracer_bullet.py:360`, `tests/test_memory.py:75`.
