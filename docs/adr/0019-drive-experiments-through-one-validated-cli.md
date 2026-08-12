# Drive experiments through one validated CLI

The executable platform will expose one `uv run llm-gs` command with run, resume, memory build, evaluate, report, inspect attempt, and validate operations. Versioned YAML Experiment Specifications are strictly validated and fully resolved into immutable Manifests; semantic overrides alter the Manifest and Experiment ID, and every live run must pass credential, schema, seed, storage, and explicit cost-limit validation before calling OpenAI.
