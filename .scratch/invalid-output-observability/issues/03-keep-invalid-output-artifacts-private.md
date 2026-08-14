# 03 — Keep Invalid-output Artifacts private

**What to build:** Analysts can see safe Invalid-output Artifact metadata in reporting while raw model response and correction-prompt content remains private to the durable workspace and never appears in exports.

**Blocked by:** 01 — Retain invalid initial proposals.

**Status:** completed

- [x] Reporting exposes safe invalid-output counts, validation/error kinds, and redacted artifact hashes without raw text.
- [x] Export bundles omit raw Invalid-output Artifact content while retaining allowed metadata and hashes.
- [x] Private workspace artifacts remain available for local diagnosis for the workspace lifetime.
- [x] Tests prove raw response text, correction prompts, and recognizable secret values cannot appear in reports or exported bundles.
