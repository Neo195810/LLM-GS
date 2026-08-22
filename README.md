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

If `conda` is not available, it is also possible to install dependencies using `pip` on **Python 3.9**:

```bash
pip install -r requirements.txt
```

LLM-GS uses a local Ollama model by default. Install Ollama, download the default model, and verify that the NVIDIA GPU is visible:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3-coder:30b
ollama ps
```

If the WSL account cannot use `sudo`, install the same official archive under the
current user's home directory instead:

```bash
mkdir -p "$HOME/.local"
curl -L https://ollama.com/download/ollama-linux-amd64.tar.zst \
  | tar --zstd -x -C "$HOME/.local"
export PATH="$HOME/.local/bin:$PATH"
ollama pull qwen3-coder:30b
```

On WSL without a running systemd service, start Ollama in a separate terminal:

```bash
OLLAMA_CONTEXT_LENGTH=8192 OLLAMA_NUM_PARALLEL=1 ollama serve
```

The local default does not require an API key. OpenAI remains available as an optional provider:

```bash
export OPENAI_KEY="YOUR_API_KEY"
python scripts/main.py --llm_provider openai
```

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

### Gradio experiment utility

Start the local dashboard from the Conda environment:

```bash
conda activate llm_gs_env
export LD_PRELOAD="$CONDA_PREFIX/lib/libstdc++.so.6"
python gradio_utility.py
```

Open `http://127.0.0.1:7860`. The utility can launch and stop every script under `scripts/`, display live candidate and best-reward events, replay Karel and MiniGrid programs, and inspect historical runs without stopping the active job. The task's stdout/stderr and tqdm progress bars are mirrored to the terminal that launched Gradio.

UI-launched experiments are isolated under `output/ui_runs/<run_id>`. Each run stores `stdout.log`, structured `events.jsonl`, and full local-model diagnostics in `llm_debug.jsonl`. Ollama requests default to 1024 output tokens and a 300-second timeout; override them through Additional CLI arguments when needed:

```text
--llm_max_tokens 2048 --llm_request_timeout 600
```

You can run revision method of the task DoorKey
```bash
# The revision scripts are in scripts/evision/run_{revision_method}.sh
bash scripts/LLM-Revision/run_regeneration.sh
```

Please note that the result of LLM-GS might not be the same as the one we reported in our paper due to the randomness of the LLMs.

The experiment results will be in the `output` directory.

### Skill-GS DoorKey MVP

This branch also includes a small Skill-GS MVP layer for the repo-native Karel
DoorKey task. It keeps the current baseline solver intact while exposing a
modular agent workflow:

```text
PlannerAgent -> SkillManagerAgent -> EvaluatorAgent -> CriticRepairAgent -> SkillMemoryAgent
```

Run the DoorKey MVP directly:

```bash
python scripts/skill_gs/run_doorkey_mvp.py --seeds 0 1 2 3 4 5 6 7 --trace-limit 0
```

Run the same loop through the explicit agent workflow:

```bash
python scripts/skill_gs/run_agent_loop.py --seeds 0 1 --skill-store data/skill_gs/doorkey_skills.json
```

Run the first adaptive retry wrapper by forcing a small first-attempt budget:

```bash
python scripts/skill_gs/run_agent_loop.py --seeds 0 --adaptive-retry --initial-max-steps 1 --retry-max-steps 200 --max-attempts 2
```

Optionally persist Adaptive Core attempt memory:

```bash
python scripts/skill_gs/run_agent_loop.py --seeds 0 --adaptive-retry --initial-max-steps 1 --retry-max-steps 200 --max-attempts 2 --attempt-memory output/skill_gs/adaptive_attempts.json --perturbation-seed 123
```

Run the fair baseline comparison used by the current demo report:

```bash
python scripts/skill_gs/run_baseline_comparison.py --seed-start 0 --seed-end 127 --initial-max-steps 10 --search-candidate-max-steps 10 20 22 24 --ours-retry-budget-schedule 20 22 24 --ours-max-attempts 4 --perturbation-seed 123 --output output/skill_gs/baseline_comparison_seed0_127.json
```

Generate the chart/report evidence pack from that comparison JSON:

```bash
python scripts/skill_gs/generate_evidence_pack.py --baseline-json output/skill_gs/baseline_comparison_seed0_127.json
```

The generated demo report is written to
`reports/skill_gs_demo_evidence_pack_2026-08-22.md`, with SVG charts under
`reports/assets/`. The current local proxy comparison shows:

```text
llm_generated one-shot proxy: 14/128 success, 128 evaluations
llm_gs_style_search proxy: 128/128 success, 512 evaluations
ours_adaptive_skill_gs: 128/128 success, 250 evaluations
```

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



## Acknowledge and licence

1. The baseline implementations in `prog_policies` are from [Reclaiming the Source of Programmatic Policies: Programmatic versus Latent Spaces](https://github.com/lelis-research/prog_policies). The baselines (CEM, CEBS, HC) code under `prog_policies` should follow the GPL-3.0 license.
2. The [HPRL](https://arxiv.org/abs/2301.12950) baseline implementation is not in this repository. We run our experiment in [this repository](https://github.com/a015kh/hprl)

## Citation

```bibtex
@inproceedings{liu2025synthesizing,
    title     = {Synthesizing Programmatic Reinforcement Learning Policies with Large Language Model Guided Search},
    author    = {Max Liu and Chan-Hung Yu and Wei-Hsu Lee and Cheng-Wei Hung and Yen-Chun     Chen and Shao-Hua Sun},
    booktitle = {The Thirteenth International Conference on Learning Representations},
    year      = {2025},
}
```
