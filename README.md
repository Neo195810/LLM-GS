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

### CLI

The `uv run llm-gs` CLI provides:

```
run              memory build     inspect attempt
resume           evaluate         validate
                 report
```

Users author versioned YAML Experiment Specifications, which resolve into immutable Experiment Manifests and IDs. Details on each subcommand, delivery slices, and verification gates are in [`docs/V2-DESIGN.md`](docs/V2-DESIGN.md).

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
