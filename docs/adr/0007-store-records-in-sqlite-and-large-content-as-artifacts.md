# Store records in SQLite and large content as artifacts

The first V2 Attempt Store will use a migrated SQLite schema in WAL mode for structured records and relationships. Large programs, model payloads, and execution trajectories will be stored as content-addressed Artifacts referenced by hash, providing transactional local queries and bounded parallelism without requiring an external database service.
