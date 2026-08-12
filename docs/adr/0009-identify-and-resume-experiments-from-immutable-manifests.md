# Identify and resume experiments from immutable manifests

V2 will resolve every experiment configuration into an immutable Experiment Manifest and derive its Experiment ID from that manifest rather than from a display name. Persisted Work Units and idempotency keys permit recovery: interrupted running work returns to pending, only transactionally completed evaluations consume Evaluation Budget, and submitted model-request costs remain recorded even if their results were never committed.
