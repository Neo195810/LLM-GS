# Sample Global Search population upfront

Global Search samples `population_size` independent Candidate Programs in a single generation, each completing its own Repair Cycle, before Search Strategy selects among them. This replaces a sequential-branching description that no longer matched the code: `cem` and `cebs` arms do not iterate proposal-repair-select across generations toward a converging distribution, as a literal cross-entropy method would. One generation is proposed, repaired, and scored, then a candidate is chosen. This is a deliberate simplification of the cross-entropy method, not the full iterative form, chosen to keep evaluation cost and memory-snapshot semantics fixed and predictable per arm rather than open-ended across generations.

Cost scales linearly with `population_size`: the candidate budget in `resolve_manifest` is sized for `population_size` independent proposal-repair sequences, so `population_size` is a direct, auditable cost lever rather than an implicit function of convergence behavior. This is hard to reverse — changing it changes the cost and semantics of every `cem`/`cebs` arm already run — and is worth recording because it is not derivable by reading `_execute_frozen_memory_protocol` in isolation.

## Consequences

The Memory Snapshot is constructed once per Execution, decoupled from the population: all `population_size` members repair against the same frozen snapshot rather than each drawing its own. This keeps the frozen-memory comparison stable across population members and avoids re-deriving a snapshot per candidate, at the cost of not modeling within-generation memory divergence. A population of exactly one reuses the initial candidate directly, preserving byte-identical behavior with the pre-#23 single-candidate path.
