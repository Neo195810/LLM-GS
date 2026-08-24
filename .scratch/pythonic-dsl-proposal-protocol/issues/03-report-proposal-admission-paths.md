# 03 — Report proposal admission paths safely

**What to build:** Researchers can see aggregate Python, backup, and normalized-backup admission
counts in execution and Matrix reporting while raw proposal pairs remain private and historical
workspaces stay compatible.

**Blocked by:** 01 — Add Pythonic proposal admission; 02 — Admit conservative DSL backups.

**Status:** completed

- [x] Each new execution records safe admission-path metadata and failed dual-path diagnostics in the existing private evidence boundary.
- [x] Public reports, exports, and Matrix aggregation expose counts only, never Python source, backup DSL, or correction text.
- [x] Historical records without admission metadata remain readable and report no fabricated path counts.
- [x] Artifact redaction, export safety, and model-output-failure behavior remain covered by existing high-level seams.
