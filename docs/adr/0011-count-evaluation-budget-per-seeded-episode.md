# Count evaluation budget per seeded episode

A Program Attempt may aggregate multiple Episode Evaluations, one for each seeded initial world, but Evaluation Budget is consumed per episode execution rather than per candidate. Outcomes are classified by versioned Task-specific rules instead of a global reward threshold, and reports include both episode and candidate counts so methods cannot hide additional evaluation cost behind larger seed batches.
