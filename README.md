# [ICLR'25] Synthesizing Programmatic Reinforcement Learning Policies with Large Language Model Guided Search

This repository officially implements [**Synthesizing Programmatic Reinforcement Learning Policies with Large Language Model Guided Search**](https://arxiv.org/abs/2405.16450).

LLM-GS combines the large language model and search algorithms for solving Programmatic Reinforcement Learning (PRL) problems. LLM-GS has a good sample efficiency in Karel environments. Also, LLM-GS shows good extensibility to novel tasks and adaptability to the novel environments of [MInigrid](https://github.com/Farama-Foundation/Minigrid).

![teaser](images/llm_gs_model.jpg)



## Getting Started (V2)

LLM-GS V2 is the actively developed research platform: a `uv`-managed CLI with structured proposal, diagnosis, and repair, an Experience Memory, and preregistered ablation matrices. See [`docs/V2-DESIGN.md`](docs/V2-DESIGN.md) for the full architecture.

### Install

V2 targets **Python 3.11** under `uv`. `pyproject.toml` and `uv.lock` are the dependency authorities.

```bash
uv sync
```

V2 calls the OpenAI API directly:

```bash
export OPENAI_KEY="YOUR_API_KEY"
```

### Architecture

Every model-generated program is stored as an immutable **Program Attempt** in an append-only Attempt Store. When a Candidate Program fails, one of four configured failure strategies decides what happens next:

- `regenerate` — start over with a fresh proposal
- `reflect` — diagnose the failure from Evaluation Evidence and repair the current program
- `memory_repair` — retrieve prior Program Attempts from Experience Memory and repair with that context
- `memory_reflect` — combine diagnosis and memory retrieval

Experience Memory runs under two isolated protocols: **Frozen Memory**, built once from training seeds and read-only during held-out evaluation, and **Online Memory**, which adapts cumulatively within a single experimental arm. The two are never mixed, so held-out results stay free of memory leakage. Search strategies (Hill Climbing, CEM, CEBS) are compared under paired Seed Suites and fixed Model/Evaluation Budgets so memory quality and search strategy aren't confounded.

### CLI

The `uv run llm-gs` CLI exposes:

| Command | Purpose |
| --- | --- |
| `validate <spec.yaml>` | Resolve a Specification into an Experiment Manifest and Experiment ID without running it |
| `run <spec.yaml> --workspace <dir>` | Run a new experiment to completion (or `--stop-after N` steps) |
| `resume --workspace <dir> --experiment-id <id>` | Continue an interrupted execution from persisted state |
| `evaluate --workspace <dir> --experiment-id <id>` | Resume through to held-out evaluation |
| `report --workspace <dir> --experiment-id <id>` | Print the reporting view for a completed or in-progress execution |
| `memory build --workspace <dir> --execution-id <id>` | Freeze a Memory Snapshot from a completed execution |
| `inspect attempt --workspace <dir> --execution-id <id>` | Dump full Program Attempt records for an execution |
| `matrix validate\|run\|report <matrix.yaml>` | Validate, execute, or report an entire ablation matrix (multiple arms in one pass) |
| `export --workspace <dir> --experiment-id <id> --output <file>` | Write a checksummed, secret-redacted export bundle |
| `import --workspace <dir> --bundle <file>` | Import an export bundle into another workspace |
| `textworld promote --evidence <file>` | Check formal TextWorld release-gate evidence before promoting the pilot to a benchmark |

Live OpenAI calls require `--enable-live-openai` plus a positive `--max-cost-usd`; without it every command runs offline against a fake client. Full command semantics, delivery slices, and verification gates are in [`docs/V2-DESIGN.md`](docs/V2-DESIGN.md).

### Experiment Specification example

Users author versioned YAML Experiment Specifications, which `validate`/`run` resolve into immutable Experiment Manifests and Experiment IDs:

```yaml
spec_version: 1
display_name: clean-house-reflect
task:
  name: CleanHouse
seeds:
  task: [7]
failure_strategy:
  name: reflect
  max_repair_cycles: 3
```

An ablation matrix specification expands one file into many arms (Tasks × Search Strategies × Failure Strategies) sharing a common Seed Suite:

```yaml
matrix_version: 1
display_name: complete-frozen-ablation
seed_suite:
  version: 1
  memory_training: [101]
  development: [102]
  held_out: [103]
search_seed: 0
replicates: [0]
max_repair_cycles: 1
```

See [`docs/specs/complete-ablation-matrix.yaml`](docs/specs/complete-ablation-matrix.yaml) for the full preregistered matrix.

### Supported tasks and search strategies

| Environment | Tasks |
| --- | --- |
| Karel | CleanHouse, FourCorners |
| MiniGrid | DoorKey, RedBlueDoor |
| TextWorld | TextWorldPilot (gated pilot; must pass the licensing and performance gates in [`docs/V2-DESIGN.md`](docs/V2-DESIGN.md) before formal use) |

Search strategies: Hill Climbing, CEM, CEBS. `offline.echo` is a fake-client-only task used for offline smoke tests and CLI examples.

## Acknowledge and licence

1. The baseline implementations in `prog_policies` are from [Reclaiming the Source of Programmatic Policies: Programmatic versus Latent Spaces](https://github.com/lelis-research/prog_policies). The baselines (CEM, CEBS, HC) code under `prog_policies` should follow the GPL-3.0 license.
2. The [HPRL](https://arxiv.org/abs/2301.12950) baseline implementation is not in this repository. We run our experiment in [this repository](https://github.com/a015kh/hprl)

See [`NOTICE`](NOTICE) for the complete third-party attribution and license review record.

## Citation

```bibtex
@inproceedings{liu2025synthesizing,
    title     = {Synthesizing Programmatic Reinforcement Learning Policies with Large Language Model Guided Search},
    author    = {Max Liu and Chan-Hung Yu and Wei-Hsu Lee and Cheng-Wei Hung and Yen-Chun     Chen and Shao-Hua Sun},
    booktitle = {The Thirteenth International Conference on Learning Representations},
    year      = {2025},
}
```
