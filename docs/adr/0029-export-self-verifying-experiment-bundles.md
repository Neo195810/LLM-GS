# Export self-verifying experiment bundles

Moving an experiment across machines requires a versioned bundle containing its Manifest, scoped structured records, Memory Snapshot, referenced Artifact hashes, and checksums rather than copying SQLite alone. Import verifies schema compatibility, hashes, and stable IDs, excludes secrets by default, and rejects conflicts instead of overwriting existing evidence.
