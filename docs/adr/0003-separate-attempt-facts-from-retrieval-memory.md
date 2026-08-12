# Separate attempt facts from retrieval memory

V2 will append every Program Attempt and its provenance to an immutable Attempt Store, while Experience Memory will be a versioned and rebuildable retrieval view containing selected or derived Memory Entries. This separation preserves experimental evidence, prevents repetitive failures from automatically flooding retrieval, and allows memory selection and retrieval strategies to change without rewriting historical facts.

Each attempt always retains an Execution Summary and deterministic replay information. Full Execution Artifacts are retained selectively for failures, leading candidates, samples, or debug runs to control storage growth. Reflection and repair are separate interface operations—even when one model performs both—so their individual contribution and cost can be measured through ablation.
