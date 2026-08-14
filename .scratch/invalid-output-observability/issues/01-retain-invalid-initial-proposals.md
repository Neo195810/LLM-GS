# 01 — Retain invalid initial proposals

**What to build:** An experiment operator can inspect a private Invalid-output Artifact whenever an initial proposal fails schema or DSL validation, including failures that exhaust correction before a Candidate Program exists.

**Blocked by:** None — can start immediately.

**Status:** completed

- [x] Each invalid initial response creates an append-only artifact observation before its correction request.
- [x] Observation links Execution, `initial` phase, attempt number, validation stage and error, finish reason, and token usage.
- [x] Response and correction prompt are redacted before 64 KiB bounding, hashing, and private content-addressed storage; original length and truncation state are retained.
- [x] Empty responses remain observable.
- [x] Successful raw responses are not retained.
- [x] Required artifact-persistence failure is reported as infrastructure failure; successful persistence preserves Model Output Failure classification.
- [x] Deterministic tests cover successful correction after invalid output and terminal correction exhaustion.
