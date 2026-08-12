# Build V2 as a separate package over V1 adapters

V2 will live in a new `src/llm_gs/` package while the existing V1 tree remains an executable baseline during transition. V2 initially reuses Environment, Task, DSL, and search implementations through explicit adapters, and components move into V2 only after behavioral equivalence is tested, preventing the baseline from being destroyed before controlled comparisons exist.
