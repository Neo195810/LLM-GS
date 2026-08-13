# 17 — TextWorld pilot and V1 licensing release gate

**What to build:** After the initial benchmark is complete, add only a constrained TextWorld pilot compiled from V2 DSL and decide whether it passes its formal-benchmark gates; separately close the V1 reuse attribution/licensing boundary required before any V2 distribution claim.

**Blocked by:** 16 — Full paired ablation matrix.

**Status:** blocked

**Acceptance criteria:**

- [ ] The TextWorld pilot uses a short fixed-vocabulary quest, bounded predicates/actions, and explicit win/fail facts through the V2 adapter boundary.
- [ ] Promotion to a formal benchmark requires Python 3.11 installation, license review, 100-seed cross-process replay, structured-evidence, and measured performance gates.
- [ ] Craftax and HighwayEnv remain alternatives rather than silently replacing initial benchmark environments.
- [ ] Reused V1 component attribution and GPL-3.0-compatible distribution obligations are documented in appropriate license/notice material before distribution is claimed.
