# Use one workspace Attempt Store

A V2 workspace will use one migrated SQLite Attempt Store whose records remain isolated by Experiment and Execution IDs, enabling cross-run memory construction and comparison without copying databases. Tests use isolated temporary stores, experiments can be exported or imported with referenced Artifacts, and multi-user authorization is outside the first release.
