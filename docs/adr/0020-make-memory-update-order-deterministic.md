# Make memory update order deterministic

Frozen Memory experiments may use bounded local parallelism because every worker reads the same immutable Snapshot. Online Memory runs sequentially in the first release; future parallel execution must use explicit batches whose workers read one Snapshot and whose results commit in stable order to a new Snapshot, so wall-clock completion order cannot alter experimental behavior.
