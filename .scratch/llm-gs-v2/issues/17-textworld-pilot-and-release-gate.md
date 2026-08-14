# 17 — TextWorld pilot and V1 licensing release gate

**What to build:** After the initial benchmark is complete, add only a constrained TextWorld pilot compiled from V2 DSL and decide whether it passes its formal-benchmark gates; separately close the V1 reuse attribution/licensing boundary required before any V2 distribution claim.

**Blocked by:** 16 — Full paired ablation matrix.

**Status:** done

**Acceptance criteria:**

- [x] The TextWorld pilot uses a short fixed-vocabulary quest, bounded predicates/actions, and explicit win/fail facts through the V2 adapter boundary. Verified: `src/llm_gs/textworld_pilot.py` (`TextWorldPilotAdapter`, frozen `key`/`chest` vocabulary).
- [x] Promotion to a formal benchmark requires Python 3.11 installation, license review, 100-seed cross-process replay, structured-evidence, and measured performance gates. Verified: `src/llm_gs/textworld_release_gate.py` `evaluate_release_gate`; passing run recorded in `docs/release-gates/textworld-release-evidence.json` (`llm-gs textworld promote` → `{"passed": true, "unmet_requirements": []}`).
- [x] Craftax and HighwayEnv remain alternatives rather than silently replacing initial benchmark environments. Verified: `docs/release-gates/textworld-pilot.md` lines 4-6.
- [x] Reused V1 component attribution and GPL-3.0-compatible distribution obligations are documented in appropriate license/notice material before distribution is claimed. Verified: `NOTICE` (V1 `prog_policies` GPL-3.0 attribution + TextWorld transitive-dependency license review, recorded 2026-08-14).
