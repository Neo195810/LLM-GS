# Fix role-specific OpenAI prompts per experiment

All LLM roles in the primary V2 experiments will use the same pinned OpenAI model and inference parameters, while proposal, diagnosis, and repair each use a distinct prompt template committed to version control. Prompts are not general plugins: an Experiment Manifest pins their hashes, and only an explicit prompt-ablation experiment may select another preregistered template version.
