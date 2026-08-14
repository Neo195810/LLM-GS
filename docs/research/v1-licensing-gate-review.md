# V1 Licensing Release Gate — Research Review (Issue #18)

Status: research inventory only. No legal conclusions are asserted. This
document exists to give a qualified legal reviewer the concrete technical
facts needed to determine whether V1/V2's reuse of `prog_policies` creates
GPL-3.0 distribution obligations, and to inventory what attribution/NOTICE
work is outstanding before any release.

This document does not modify `LICENSE`, `NOTICE`, or any code, and does not
itself close the acceptance criteria in issue #18 — it supplies the evidence
those criteria call for.

## 1. Inventory of reused `prog_policies` components actually imported by this repo

Grep of `src/llm_gs/*.py` and `tests/*.py` for `prog_policies` imports
(command: `grep -rn "prog_policies" src/ tests/`), captured verbatim:

| Importing file | Imported symbol(s) | Source module |
|---|---|---|
| `src/llm_gs/v1_adapter.py:7` | `BaseTask` | `prog_policies.base.task` |
| `src/llm_gs/v1_adapter.py:8` | `create_replay_environment` | `prog_policies.runtime` |
| `src/llm_gs/minigrid_red_blue_door.py:12` | `MinigridDSL` | `prog_policies.minigrid.dsl` |
| `src/llm_gs/minigrid_red_blue_door.py:13` | `ProgramWrapper` | `prog_policies.minigrid.wrapper` |
| `src/llm_gs/minigrid_red_blue_door.py:14` | `RedBlueDoor` | `prog_policies.minigrid_tasks.redbluedoor` |
| `src/llm_gs/proposer.py:13` | `KarelDSL` | `prog_policies.karel.dsl` |
| `src/llm_gs/proposer.py:14` | `MinigridDSL` | `prog_policies.minigrid.dsl` |
| `src/llm_gs/minigrid_door_key.py:13` | `MinigridDSL` | `prog_policies.minigrid.dsl` |
| `src/llm_gs/minigrid_door_key.py:14` | `ProgramWrapper` | `prog_policies.minigrid.wrapper` |
| `src/llm_gs/ast_features.py:6` | `KarelDSL` | `prog_policies.karel.dsl` |
| `src/llm_gs/ast_features.py:7` | `MinigridDSL` | `prog_policies.minigrid.dsl` |
| `tests/test_replay_and_ui.py:10` | `KarelDSL` | `prog_policies.karel` |
| `tests/test_replay_and_ui.py:11` | `MinigridDSL` | `prog_policies.minigrid.dsl` |
| `tests/test_replay_and_ui.py:12` | `create_replay_environment` | `prog_policies.runtime` |
| `tests/test_replay_and_ui.py:13` | `load_historical_events`, `render_program_gif` | `prog_policies.utils.replay` |
| `tests/test_v1_adapter_equivalence.py:9` | `BaseTask` | `prog_policies.base` |
| `tests/test_v1_adapter_equivalence.py:10` | `create_replay_environment` | `prog_policies.runtime` |

Note the issue's premise ("CEM, CEBS, hill-climbing baselines") describes the
*research purpose* of the vendored `search_methods/` package
(`prog_policies/search_methods/{cem,cebs,hill_climbing,hill_climbing_latent,scheduled_hill_climbing}.py`),
but this repo's own `src/`/`tests/` code does not currently import
`prog_policies.search_methods` directly — the direct imports actually
exercised are the DSL (`karel.dsl`, `minigrid.dsl`), environment/task base
classes (`base.task`, `base`), the minigrid wrapper/task classes, the replay
runtime (`prog_policies.runtime`), and replay utilities
(`prog_policies.utils.replay`). The `search_methods/` and `search_space/`
subpackages are present in the vendored tree and packaged
(`pyproject.toml:35`, see §4) but were not found imported from `src/` or
`tests/` at time of review — a legal reviewer should not assume the reuse is
limited to what is directly imported, since packaging (§4) distributes the
entire `prog_policies/` tree regardless of which parts are imported at
runtime.

## 2. Embedded copyright/license notices in the local vendored copy

Searched: `grep -rniE "copyright|license|gpl|mit license|apache" prog_policies --include="*.py"` — **zero matches** across the entire vendored tree.

Searched for notice/metadata files: `find prog_policies -iname "*license*" -o -iname "*copying*" -o -iname "readme*" -o -iname "setup.py" -o -iname "pyproject.toml"` — **zero matches**.

The locally vendored `prog_policies/` directory (see file listing in §4)
contains no `LICENSE`, `COPYING`, `README`, `setup.py`, or `pyproject.toml`
of its own, and no per-file copyright/license header was found in any
`.py` file. There is no embedded attribution of any kind in the vendored
copy — the only attribution present anywhere in this repo is the one
paragraph in the root `NOTICE` file (`NOTICE:3-6`) naming the upstream
project and URL.

## 3. Upstream repository's actual declared license (primary source)

Fetched via `gh api` (GitHub REST API, live network access confirmed working):

- `gh api repos/lelis-research/prog_policies --jq '{license: .license, ...}'` →
  ```json
  {"license":{"key":"gpl-3.0","name":"GNU General Public License v3.0","spdx_id":"GPL-3.0"}}
  ```
- `gh api repos/lelis-research/prog_policies/license` →
  ```json
  {"html_url":"https://github.com/lelis-research/prog_policies/blob/main/LICENSE","name":"GNU General Public License v3.0","spdx_id":"GPL-3.0"}
  ```
- Root directory listing (`gh api repos/lelis-research/prog_policies/contents/`)
  confirms a `LICENSE` file exists at the upstream repo root, alongside
  `README.md`, `data`, `environment.yml`, `leaps` (a git submodule —
  upstream's own `.gitmodules` references `leaps`, distinct from this
  repo's own `leaps` submodule pointing to
  `https://github.com/Tales-Carvalho/leaps`), `output`, `params`,
  `prog_policies`, `requirements.txt`, `sample_args`, `scripts`, `slurm`,
  `tests`.
- Upstream README (fetched via `gh api repos/lelis-research/prog_policies/readme`)
  identifies the project as implementing "Reclaiming the Source: Programmatic
  versus Latent Search Spaces," ICLR 2024
  (https://openreview.net/forum?id=NGVljI6HkR), with repo description
  "Author: Tales Carvalho."

**Finding: upstream `lelis-research/prog_policies` does declare GPL-3.0 at
its repository root** (`LICENSE` file, GitHub-detected as GPL-3.0/SPDX
`GPL-3.0`). This directly answers the open question in the issue: it is not
unknown or unreachable — network access via `gh api` succeeded and returned
an authoritative GitHub license-detection result plus the file's URL. What
remains unconfirmed by this review is the **exact license text/version
variant** (e.g. GPL-3.0-only vs GPL-3.0-or-later) and any additional
per-file notices upstream may carry that GitHub's license detector would not
surface — a reviewer should fetch and read
`https://github.com/lelis-research/prog_policies/blob/main/LICENSE` in full
before finalizing NOTICE language.

Also notable: this repo's current `NOTICE` (`NOTICE:8-9`) already states the
reused code "is treated as GPL-3.0 compatible material" without citing this
GitHub license-detection result or the upstream LICENSE file URL directly —
that citation gap is real (as the issue assumed) even though the underlying
GPL-3.0 claim about upstream turns out to be correct and now has a citable
primary source.

## 4. Technical facts for the in-process-import / distribution analysis

These are the facts a legal reviewer needs; this review does not draw a
conclusion from them.

- **In-process import, not subprocess.** Confirmed: `src/llm_gs/v1_adapter.py:7-8`
  does `from prog_policies.base.task import BaseTask` and
  `from prog_policies.runtime import create_replay_environment` — ordinary
  Python module imports executed in the same interpreter process as this
  repo's own code, not a subprocess/CLI/RPC boundary. The same pattern holds
  for every import listed in §1.
- **Vendored (copied into this repo's own git history), not an external
  dependency.** `git log --diff-filter=A --oneline -- prog_policies/runtime.py`
  shows the file was added directly in commit `179ef24` ("Add local Ollama
  inference and Gradio experiment dashboard"), and `prog_policies/` is not
  listed in `.gitmodules` (which only declares a `leaps` submodule, unrelated
  to `prog_policies`). `git ls-files prog_policies | head` confirms the
  files are ordinary tracked blobs in this repo, not a submodule pointer.
  `prog_policies` is not installed via `pip`/`requirements.txt` — it ships as
  part of this repo's own source tree.
- **Distributed as part of this project's own package.** `pyproject.toml:35`
  sets `packages = ["src/llm_gs", "prog_policies"]` — i.e. any build/release
  of this project's Python package would bundle the entire vendored
  `prog_policies/` tree (all subdirectories listed in the file inventory
  below), not just the modules directly imported by `src/`.
- **Modifications made to the vendored copy vs. upstream.** The commit that
  introduced `prog_policies/` into this repo (`179ef24`) already contains
  local edits layered on top of the vendored files in the same commit:
  `prog_policies/base/task.py` (modified, +4/-... lines),
  `prog_policies/karel/environment.py` (modified),
  `prog_policies/minigrid/wrapper.py` (extended, +15 lines),
  `prog_policies/runtime.py` (new file, +71 lines, not present in this form
  upstream), `prog_policies/search_methods/base_search.py` (modified,
  +19 lines), `prog_policies/utils/__init__.py` (modified),
  `prog_policies/utils/experiment_events.py` (new file, +182 lines),
  `prog_policies/utils/replay.py` (new file, +86 lines). This confirms the
  local copy is not a pristine, unmodified vendoring of upstream — it is a
  modified/derived copy, with new files added inside the `prog_policies`
  package namespace that do not exist in upstream's `scripts`/`tests`-style
  layout.
- **What was and wasn't carried over from upstream.** The locally vendored
  `prog_policies/` directory (file inventory: `base/`, `karel/`,
  `karel_tasks/`, `latent_space/`, `minigrid/`, `minigrid_tasks/`,
  `runtime.py`, `search_methods/`, `search_space/`, `utils/`) mirrors
  upstream's `prog_policies/` subpackage, but the upstream repo's root-level
  `LICENSE` file, `README.md`, `scripts/`, `tests/`, `sample_args/`,
  `environment.yml`, and `leaps` submodule were **not** copied into this
  repo's `prog_policies/` directory — only the importable Python package
  contents were vendored. This is the direct, concrete explanation for why
  no LICENSE/COPYING file exists inside the local `prog_policies/`
  directory today: it was never carried over, even though it exists at the
  upstream repo root.

## 5. Open questions requiring qualified legal review

The following are explicitly **not resolved** by this review and are handed
to a qualified legal reviewer, per issue #18's instruction that this is a
legal question and not one an AI agent should conclude on:

1. **Does in-process Python import of GPL-3.0-licensed `prog_policies` code
   into this repository's own modules (§4) create a combined/derivative work
   for GPL-3.0 "distribution" purposes when this repository (or its built
   package, given `pyproject.toml:35`) is itself distributed?** This review
   only establishes the technical facts (in-process import; vendored, not
   subprocess-isolated; packaged together) — it does not conclude whether
   GPL-3.0's copyleft/distribution obligations are triggered, under what
   conditions, or what the scope of "the work" would be for compliance
   purposes.
2. **Exact upstream license terms.** This review confirms GitHub's license
   detector reports upstream as GPL-3.0 (SPDX `GPL-3.0`) and cites the file
   URL (§3), but a reviewer should fetch and read the full text at
   `https://github.com/lelis-research/prog_policies/blob/main/LICENSE`
   to confirm the exact version/variant (e.g., "or later" language) and
   whether any supplementary terms exist, since GitHub's badge is a
   best-effort detection, not a legal reading.
3. **Whether NOTICE's current attribution is sufficient**, or whether GPL-3.0
   compliance (if triggered) requires additional steps such as: including a
   copy of the upstream LICENSE text specifically alongside the vendored
   `prog_policies/` subtree (not just the umbrella repo-root `LICENSE`),
   documenting author/copyright holder attribution for `prog_policies`
   specifically (upstream's GitHub description names "Tales Carvalho" as
   author — this is not currently reflected anywhere in this repo's NOTICE),
   and/or providing "complete corresponding source" for the modified files
   identified in §4 in the form GPL-3.0 requires.
4. **Whether the currently-unimported-but-vendored-and-packaged
   `search_methods/`, `search_space/`, `latent_space/`, `karel_tasks/`, and
   `minigrid_tasks/` subpackages** (present in the tree, listed in the
   package manifest at `pyproject.toml:35`, but not directly imported by
   `src/` or `tests/` per §1) need to be excluded from any V2 distribution
   package, or whether their mere inclusion in the packaged tree is itself
   enough to trigger the same distribution analysis as the modules that are
   directly imported.
5. **Scope of "distribution."** This review does not evaluate whether any
   currently planned or executed activity (e.g., internal experiment runs,
   data export, CI) constitutes "distribution" under GPL-3.0 — per issue
   #18, that determination, and this issue generally, is scoped to blocking
   *software release/distribution*, not internal experiment execution or
   self-verifying data export. A reviewer should confirm which of this
   project's current or planned activities (e.g., a `pip install`-able
   package build, a public GitHub repo push, a container image, an academic
   artifact release) actually constitute "distribution" in the relevant
   legal sense before treating any specific activity as gated or not gated
   by this finding.

## 6. Release-gate status

Per issue #18's acceptance criterion "Release automation or documentation
clearly blocks unsupported closed or differently licensed distribution":
this review does not itself add or verify any such blocking mechanism in
release automation or documentation — that is a separate, not-yet-verified
piece of work. The existing `NOTICE` file (`NOTICE:9-14`) states a
procedural requirement that "release owners must review the provenance and
licenses of every reused component and dependency ... and obtain explicit
legal clarification before distributing under closed or otherwise
incompatible terms," but this review did not find an automated (CI/build-time)
enforcement mechanism for that requirement — only documentation/policy text.
Whether that is sufficient to satisfy the acceptance criterion, or whether
automated enforcement (e.g., a release-gate check) is required, is itself
a candidate follow-up item, not resolved here.

## Sources cited in this document

- `src/llm_gs/v1_adapter.py:7-8`
- `src/llm_gs/minigrid_red_blue_door.py:12-14`
- `src/llm_gs/proposer.py:13-14`
- `src/llm_gs/minigrid_door_key.py:13-14`
- `src/llm_gs/ast_features.py:6-7`
- `tests/test_replay_and_ui.py:10-13`
- `tests/test_v1_adapter_equivalence.py:9-10`
- `pyproject.toml:35`
- `NOTICE:1-38` (full file, this repo root)
- `LICENSE:1-4` (this repo root, GPL-3.0 verbatim text)
- Local shell command: `git log --diff-filter=A --oneline -- prog_policies/runtime.py` → commit `179ef24`
- Local shell command: `git show --stat 179ef24` (file-level diff of the commit that introduced `prog_policies/`)
- `.gitmodules` (this repo root; confirms `prog_policies` is not a submodule)
- `gh api repos/lelis-research/prog_policies` (fetched live, this review)
- `gh api repos/lelis-research/prog_policies/license` (fetched live, this review)
- `gh api repos/lelis-research/prog_policies/contents/` (fetched live, this review)
- `gh api repos/lelis-research/prog_policies/readme` (fetched live, this review)
- https://github.com/lelis-research/prog_policies (upstream repo)
- https://github.com/lelis-research/prog_policies/blob/main/LICENSE (upstream LICENSE file — GPL-3.0 per GitHub license detection; full text not independently re-read by this review, see open question 2)
- https://openreview.net/forum?id=NGVljI6HkR (upstream paper referenced in upstream README)
