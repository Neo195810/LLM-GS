# 02 — Retain invalid repair outputs

**What to build:** An experiment operator can inspect the same private Invalid-output Artifact sequence when a Reflector/Repairer emits invalid output, including repair failures after a valid Candidate Program and later successful corrections.

**Blocked by:** 01 — Retain invalid initial proposals.

**Status:** completed

- [x] Repair-phase invalid responses retain the same redacted, bounded, append-only evidence as initial proposals.
- [x] Every repair artifact links the durable Execution, `repair` phase, and correction-attempt number.
- [x] Artifact persistence occurs before each repair correction request and does not depend on a successful Repair Attempt.
- [x] Resumable execution and matrix paths preserve the expected model-output versus infrastructure failure classification.
- [x] Tests cover repair exhaustion, eventual repair success, empty output, and failed artifact persistence.
