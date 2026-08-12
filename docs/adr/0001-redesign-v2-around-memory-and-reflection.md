# Redesign V2 around memory and reflection

LLM-GS V2 may break V1's internal architecture and configuration formats so that Experience Memory, Reflection, and search methods become replaceable research components. V1 remains available as a read-only baseline, with explicit result conversion when comparison is required; V1 outputs are not inserted directly into V2 Experience Memory because their provenance and semantics are not guaranteed to match.
