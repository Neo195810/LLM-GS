# Isolate memory lineages between experimental arms

Primary Frozen Memory comparisons use one independently generated and locked Snapshot shared by every search algorithm and treatment. Online experiments fork that same starting Snapshot into a separate Memory Lineage for each method, algorithm, and replicate; entries never flow between arms or replicates. Memory Entries retain their source Search Strategy and may transfer across algorithms, allowing cross-search generalization to be measured without giving any arm different source material.
