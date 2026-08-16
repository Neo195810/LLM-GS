# [ICLR'25] Synthesizing Programmatic Reinforcement Learning Policies with Large Language Model Guided Search

This repository officially implements [**Synthesizing Programmatic Reinforcement Learning Policies with Large Language Model Guided Search**](https://arxiv.org/abs/2405.16450).

LLM-GS combines the large language model and search algorithms for solving Programmatic Reinforcement Learning (PRL) problems. LLM-GS has a good sample efficiency in Karel environments. Also, LLM-GS shows good extensibility to novel tasks and adaptability to the novel environments of [MInigrid](https://github.com/Farama-Foundation/Minigrid).

![teaser](images/llm_gs_model.jpg)



## Getting Started

### Clone

After you download the repo, please initialize the leaps submodule.
```bash
git submodule update --init --recursive
```

### Dependencies

We recommend using `conda` to install the dependencies:

```bash
conda env create --name llm_gs_env --file environment.yml
pip install -r requirements.txt
```

If `conda` is not available, it is also possible to install dependencies using `pip` on **Python 3.8**:

```bash
pip install -r requirements.txt
```

The current LLM backend is [Ollama](https://ollama.com/). Install and start
Ollama, then download both the configured generation model and the embedding
model used by Skill RAG:
```bash
ollama pull qwen3-coder:30b
ollama pull nomic-embed-text
```

`qwen3-coder:30b` is configured in `llm/llm_program_generator.py`. If you use
a different local model, update that constant before running an experiment.

### Execution
To execute our main method and baselines. You can change **method** and **task** inside the scripts. **(LLM-GS is our main method.)**

```bash
bash scripts/run_main_results.sh
```

Or you can run specific algorithm and tasks
```bash
# All scripts are in scripts/{baseline}/run_{task}.sh
bash scripts/LLM-GS/run_DoorKey.sh
```

You can run revision method of the task DoorKey
```bash
# The revision scripts are in scripts/evision/run_{revision_method}.sh
bash scripts/LLM-Revision/run_regeneration.sh
```

Please note that the result of LLM-GS might not be the same as the one we reported in our paper due to the randomness of the LLMs.

The experiment results will be in the `output` directory.

## Skill RAG extension

This extension lets LLM-GS retain successful, verified DSL programs as
reusable skills. A successful final program and its non-trivial control-flow
subprograms are saved in `output/skills.json` with their task description,
reward, DSL source and Ollama embedding. On a later task, the library uses
cosine similarity to retrieve the most relevant same-environment skills. They
are injected into the LLM prompt and also evaluated as hill-climbing seeds.

Run with Skill RAG enabled:

```bash
python scripts/main.py --task DoorKey --seed 0 \
  --use_skill_library \
  --skill_library_path output/skills.json \
  --skill_top_k 3 \
  --output_name Skill-RAG
```

Useful options are `--skill_embedding_model` (default:
`nomic-embed-text`) and `--skill_min_reward` (default: `1.0`). The run log
records retrieved skills and their similarity scores for auditing. See
[`prog_policies/skills/README.md`](prog_policies/skills/README.md) for the
storage format, experimental protocol and integration details.

For a fair transfer experiment, build the library with source tasks and hold
out the target task. Reusing a solved DoorKey program for DoorKey measures
same-task memory reuse rather than cross-task generalization.

## Adapting LLM-GS to Your Environment

To use LLM-GS for your custom PRL task:

1. **Define your DSL**
   Create a new DSL in `prog_policies/your_dsl/` and specify production rules.

2. **Register your environment**
   Add it to `prog_policies/utils/__init__.py`.

3. **Implement your PRL environment**
   - Write your environment in `prog_policies/your_environment/`
   - Option A: Subclass `BaseEnvironment` in `prog_policies/base/environment.py`  
   - Option B: Use `gymnasium.core.Wrapper`

4. **Write your prompt template**
   Follow `llm/prompt_template.py` structure to write your system prompt and user prompt.

5. **Set up search space (if needed)**
   Create a custom search space in `prog_policies/search_space`. You can specify your mutation method here for local search. If the production rules are more complicated than Karel's, writing your own search space is necessary.

6. **Parse LLM output**
   Use `convert()` and `get_program_str_from_llm_response_dsl()` in `llm/utils.py` to post-process Python and DSL programs.



## Acknowledgement and licence

1. The baseline implementations in `prog_policies` are from [Reclaiming the Source of Programmatic Policies: Programmatic versus Latent Spaces](https://github.com/lelis-research/prog_policies), which is licensed under GPL-3.0. Keep its copyright and licence notices intact, and distribute modifications to that GPL-covered code under GPL-3.0 when redistributing the combined work.
2. The [HPRL](https://arxiv.org/abs/2301.12950) baseline implementation is not in this repository. We run our experiment in [this repository](https://github.com/a015kh/hprl)
3. The Skill RAG extension was inspired by the skill-library retrieval pattern
   in [Voyager](https://github.com/MineDojo/Voyager). It is an independent
   implementation and does not copy Voyager source code.

## Citation

```bibtex
@inproceedings{liu2025synthesizing,
    title     = {Synthesizing Programmatic Reinforcement Learning Policies with Large Language Model Guided Search},
    author    = {Max Liu and Chan-Hung Yu and Wei-Hsu Lee and Cheng-Wei Hung and Yen-Chun     Chen and Shao-Hua Sun},
    booktitle = {The Thirteenth International Conference on Learning Representations},
    year      = {2025},
}
```
