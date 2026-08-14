# Handoff: `nrnmnrn/llm-gs-v2` environment synchronization

## Current state

This working tree is the multi-person repository checkout, not the original standalone V2 repository.

- Target repository remote: `origin` → `https://github.com/Neo195810/LLM-GS.git`
- Source repository remote: `llm-gs` → `https://github.com/nrnmnrn/LLM-GS-V2.git`
- Current branch: `nrnmnrn/llm-gs-v2`
- Base branch: `origin/master` at `179ef24`
- Imported source branch: `llm-gs/codex/v2-spec`
- Import commit: `851c204` (`Merge remote-tracking branch 'llm-gs/codex/v2-spec' ...`)
- Imported V2 implementation commit: `1159873`

The current branch is five commits ahead of `origin/master`. The merge imported the tracked V2 documents, `pyproject.toml`, `uv.lock`, `src/llm_gs/`, and the offline tracer-bullet tests. The working tree was clean when this handoff was written.

The source remote is intentionally configured to fetch only `codex/v2-spec`; do not fetch or merge `llm-gs/master` unless the user explicitly requests it.

## User intent

The user completed the merge into the multi-person repository's child branch, but reports that several environment/setup files from the standalone LLM-GS-V2 project are not present on this branch. The next agent should audit and complete the synchronization.

The child branch is the user's project branch. It must not modify `origin/master`.

## Important constraints

1. Preserve the multi-person repository's `requirements.txt` exactly as it exists on `origin/master`.
   Check with:

   ```bash
   git diff origin/master...HEAD -- requirements.txt
   git diff origin/master -- requirements.txt
   ```

   If there is a conflict, resolve it in favor of `origin/master` unless the user gives a new instruction.

2. V2's authoritative environment is `uv` + Python 3.11, represented by `.python-version`, `pyproject.toml`, and `uv.lock`. Do not reintroduce Conda as the V2 setup mechanism.

3. Do not blindly copy every dotfile from the standalone repository. In particular, `.agents/` and `skills-lock.json` were untracked in the standalone checkout and therefore were not part of the Git merge. Determine whether they are local agent tooling or intended shared repository configuration before adding them.

4. Do not overwrite V1 environment files (`environment.yml`, the shared `requirements.txt`) merely to make the V2 package environment work. Keep V1 compatibility and V2 reproducibility explicit and documented.

5. Keep generated/runtime data, secrets, API keys, model payloads, databases, and virtual environments out of Git.

## Likely cause of the missing setup

The merge transferred Git-tracked files only. The standalone V2 checkout had local untracked files (`.agents/` and `skills-lock.json`), so Git had no commits to transfer for them. This does not necessarily mean they should be added to the shared repository; inspect their purpose first.

## Required audit

Compare the target branch with both its base and the source branch:

```bash
git diff --name-status origin/master...HEAD
git ls-tree -r --name-only HEAD
git ls-tree -r --name-only llm-gs/codex/v2-spec
git status --short --untracked-files=all
```

Audit at least:

- `.python-version`, `pyproject.toml`, `uv.lock`
- shared `requirements.txt` and V1 `environment.yml`
- package entry points and `src/llm_gs/`
- test discovery and test configuration
- `.gitignore`
- CI/workflow files under `.github/`
- README/setup instructions
- agent/issue-tracker documentation under `AGENTS.md` and `docs/agents/`
- whether `.agents/` or `skills-lock.json` should be shared, ignored, or documented separately

Use file hashes and diffs where possible; do not infer that two files are equivalent from their names alone.

## Expected implementation outcome

After the audit, make the smallest set of changes needed so a fresh clone of `nrnmnrn/llm-gs-v2` can:

1. install/run V2 with `uv` and Python 3.11;
2. retain the exact `origin/master` `requirements.txt`;
3. run the existing V2 checks (`uv run pytest -q`, `uv run mypy src tests`, and `uv run ruff check src tests`);
4. still run or clearly preserve the multi-person repo's existing V1 test/setup expectations;
5. explain any intentionally excluded local-only files.

If a setup file must differ between V1 and V2, document the boundary instead of silently replacing the main branch's file.

## Verification and delivery

Before committing:

```bash
git diff --check
git diff origin/master -- requirements.txt
uv run pytest -q
uv run mypy src tests
uv run ruff check src tests
git status --short --branch
```

Commit only the audited synchronization changes on `nrnmnrn/llm-gs-v2`. Do not push or alter `origin/master` without an explicit user request.
