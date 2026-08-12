# Modernize the V2 runtime under uv

V2 will target Python 3.11 and use `pyproject.toml` plus `uv.lock` as its authoritative environment, upgrading dependencies rather than inheriting V1's Python 3.8/3.9, Torch 1.10, and Gym 0.15 constraints. V1 adapters run in the same runtime when deterministic equivalence can be preserved; an explicit subprocess environment is a fallback only for components proven impossible to migrate.
