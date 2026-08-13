# LLM-GS Skill Library

This module adds a persistent, verified skill memory to LLM-GS.  A **skill**
is a complete executable DSL program derived from a successful search result,
or a non-trivial statement subtree wrapped in `DEF run m( ... m)`.  This makes
every retrieved item syntactically valid and usable both as prompt context and
as a hill-climbing seed.

## What is implemented

1. After a task reaches `skill_min_reward` (default: `1.0`),
   `SkillLibrary.extract_and_store()` stores the final program and its
   reusable control-flow fragments.
2. Skills are stored in an inspectable JSON file (default:
   `output/skills.json`) with the DSL program, a generated description,
   source task, best reward and usage count.
3. Before a new task, `SkillLibrary.retrieve()` ranks skills from the same DSL
   environment and returns the top-k results.
4. Retrieved skills are injected into the LLM prompt and evaluated as complete
   initial programs for local search.

Skills are retrieved through an Ollama embedding model (`nomic-embed-text` by
default), ranked by cosine similarity.  The vector is persisted alongside the
JSON metadata; no separate vector-database service is required.

## Run

Build a library while solving a task:

```powershell
python scripts/main.py --task DoorKey --seed 0 `
  --use_skill_library `
  --skill_library_path output/skills.json `
  --skill_top_k 3
```

Before the first skill-RAG run, download the embedding model once:

```powershell
ollama pull nomic-embed-text
```

Relevant arguments:

| Argument | Meaning |
| --- | --- |
| `--use_skill_library` | Enables retrieval, prompt injection, search seeding and post-success storage. |
| `--skill_library_path` | Shared JSON file containing skills. |
| `--skill_top_k` | Number of retrieved skills, default `3`. |
| `--skill_min_reward` | Minimum verified task reward required before saving, default `1.0`. |
| `--skill_embedding_model` | Ollama embedding model, default `nomic-embed-text`. |

The run log records the exact `retrieved_skills`, so retrieval can be audited
after an experiment.

## Main-branch integration

To integrate this feature, include the following changes:

1. Add `prog_policies/skills/__init__.py` and `prog_policies/skills/library.py`.
2. In `scripts/main.py`, add the four CLI arguments above; create a
   `SkillLibrary`; retrieve skills before LLM generation; append parsed skills
   to `program_list`; and store `best_prog` after successful completion.
3. In `llm/llm_program_generator.py`, accept `retrieved_skills` in
   `LLMProgramGenerator.__init__` and append `SkillLibrary.prompt_block(...)`
   to the `python_to_dsl` user prompt.
4. Add `tests/test_skill_library.py` and run:

   ```powershell
   python -m unittest tests/test_skill_library.py
   ```

Do **not** merge unrelated local backend/environment changes when moving this
feature (for example OpenAI-to-Ollama edits).  The skill module itself has no
new third-party dependency.

## Experimental protocol

Use the same task budgets, LLM parameters and seeds for both conditions:

| Condition | Command option |
| --- | --- |
| No memory | omit `--use_skill_library` |
| Embedding skill RAG | `--use_skill_library` |

Report: (1) program evaluations to first reward `1.0`, (2) success rate under
a fixed evaluation budget, and (3) reward-versus-evaluations AUC.  Run several
seeds and report mean/median with spread.

When evaluating cross-task generalization, do not put the target task's own
solutions in the library.  Use a leave-one-task-out setup: learn skills from
the source tasks, then retrieve only those skills for the held-out target task.
Running DoorKey with already-solved DoorKey skills is still useful, but it
measures same-task memory reuse rather than generalization.

## Voyager-style RAG design

[Voyager](https://github.com/MineDojo/Voyager) stores executable skills with
natural-language descriptions and retrieves relevant skills through a vector
database.  This implementation follows the same retrieval pattern, adapted to
the smaller LLM-GS collection:

1. Embed `task description + skill description + DSL program` at storage time.
2. Persist vectors in `skills.json` beside portable metadata.
3. Embed the current task; retrieve same-environment top-k skills by cosine
   similarity; log each similarity score.

Each selected skill is still injected into the LLM prompt and used as a local
search seed, preserving compositional reuse.
