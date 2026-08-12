# LLM-GS V2 Design

## Initial scope

V2 is an executable, locally recoverable research platform for testing whether Experience Memory and failure-driven repair improve programmatic policy synthesis. It supports Karel CleanHouse and FourCorners, MiniGrid DoorKey and RedBlueDoor, and compares Hill Climbing, CEM, and CEBS under paired Seed Suites and fixed budgets.

The initial OpenAI model is `gpt-5.6-luna` with reasoning effort `medium`. V2 executes model-generated DSL only, uses structured proposal, diagnosis, and repair outputs, and does not use embedding retrieval.

V2 targets Python 3.11 under `uv`. `pyproject.toml` and `uv.lock` are the V2 dependency authorities; legacy requirements and Conda metadata remain only for the V1 transition. V2 calls the official OpenAI Python SDK directly, while LangChain remains confined to the V1 baseline.

Karel and MiniGrid remain the initial benchmark environments for V1 comparability. After the initial slices work end to end, V2 adds one constrained TextWorld pilot with a 10–30-step quest, fixed vocabulary, bounded predicates and actions, and explicit win and fail facts. TextWorld commands remain compiled from V2 DSL rather than emitted as arbitrary natural language. The pilot becomes a formal benchmark only after passing Python 3.11 installation and licensing review, 100-seed cross-process replay, structured-evidence coverage, and measured performance gates. Craftax is the fallback for long-horizon throughput and HighwayEnv for continuous-state safety control.

## Executable surface

The `uv run llm-gs` CLI provides `run`, `resume`, `memory build`, `evaluate`, `report`, `inspect attempt`, and `validate`. Users author versioned YAML Experiment Specifications, which resolve into immutable Experiment Manifests and IDs.

## Delivery slices

1. Establish the `uv` package, Manifest resolution, SQLite and Artifact storage, CLI, and fake OpenAI client.
2. Run Karel CleanHouse with Hill Climbing through Regenerate and Reflect.
3. Add the Attempt Store, Memory Curator, Structured Retrieval, Memory Repair, and Memory + Reflect.
4. Add Frozen and Online protocols, recovery, and reports.
5. Add FourCorners, DoorKey, and RedBlueDoor.
6. Add CEM, CEBS, and the full ablation matrix.

Every slice ends in an executable experiment and automated acceptance checks.

## Model output handling

Proposal, Diagnosis, and repair use role-specific schemas and fixed sampling parameters across comparison groups. A logical request may make at most two format-correction requests using only validation errors and the original response. Every request consumes Model Budget; exhaustion produces a Model Output Failure rather than a Program Attempt.

Role-specific input and output token limits are calibrated on pilot and development activity to be sufficient rather than maximal. Output limits cover at least the observed normal-response P99 plus 20–30 percent headroom. Input limits cover the P99 of normal prompts with permitted memory and evidence while retaining an explicit cost ceiling. Reaching 80 percent emits a recorded warning; at 100 percent, a deterministic trimming policy runs, and the request is blocked if it still does not fit. Limits are frozen before held-out evaluation and cannot be raised in response to outcomes.

An empirical P99 requires at least 100 valid development responses per role across representative Tasks. With fewer observations, the provisional limit is the observed maximum plus 30 percent and held-out execution remains blocked. Research budgets are enforced in requests, input tokens, output tokens, and Episode Evaluations; an execution-time price snapshot provides monetary estimates and an additional user-approved currency safety cap.

Context Trimming never removes system instructions, output schema, Task or DSL contracts, the current Candidate Program, or minimum current-failure evidence. It removes the lowest-ranked Memory Entries while preserving category minima, shortens noncritical evidence windows, and then removes representative success examples before similar failures or effective repair pairs. A request that still exceeds its limit is blocked. Every removal and the trimmer version are recorded.

Output-length termination is schema-invalid model output and may enter the two-attempt format-correction path; exhaustion becomes a Model Output Failure. Memory and evidence enter prompts only through an allowlisted, versioned serializer with stable identifiers and explicit data boundaries, never as concatenated historical instructions.

For multi-episode Diagnosis, deterministic selection includes the worst-progress episode, one representing the dominant Failure Type, one nearest median behavior, and—when behavior diverges—one contrasting outcome. Only Execution Summaries and bounded failure windows are supplied, under an Evidence Context Budget, with omitted counts recorded.

Formal executions prohibit human changes to prompts, programs, memory, or curator state. Interactive development activity is separately identified and cannot contribute to the primary Frozen Snapshot or held-out results.

Infrastructure Retry limits and backoff rules are resolved into the Experiment Manifest. Exhaustion produces an Infrastructure Failure Work Unit outcome, creates no failed Program Attempt, consumes no Episode Evaluation beyond any evaluation that already completed transactionally, and is reported separately from all Attempt Outcomes.

## Artifact retention

Execution Summaries, seeds, programs, and provenance are permanent structured records. Complete trajectories are retained for new failure types, successful programs, leading repair pairs, and deterministic samples within a configured capacity. Referenced Artifacts are not automatically deleted; cleanup may remove only unreferenced content. Diagnostic service payloads are sanitized before retention.

## Memory corpus construction

The Attempt Store preserves the naturally observed distribution. The primary Frozen Snapshot uses preregistered quotas across Tasks, Failure Types, successful examples, effective repair pairs, and Search Strategy sources while retaining source-frequency metadata. Exact duplicates require matching Experiment Context, Failure Type and Reason, Normalized AST hash, and state-feature bucket; approximate AST matches remain separate entries.

Online arms and replicates maintain isolated Memory Lineages. Formal OpenAI requests are never replayed from an application response cache, although provider-side prompt caching may be used and its token usage is recorded.

The Structured Retrieval implementation may calibrate its deterministic ordering or weights on development seeds, but its complete versioned configuration must be recorded in the Experiment Manifest and frozen before a Memory Snapshot is built for held-out evaluation. Held-out results cannot change retrieval ordering or weights.

## Verification gates

- Unit tests cover outcome classification, budgets, state transitions, memory curation and retrieval, and AST normalization.
- Property-based tests cover serialization round trips, idempotency, budget bounds, and append-only Attempt Store behavior.
- Golden tests cover fixed-world Evaluation Evidence, prompt payloads, and reports.
- Integration tests cover SQLite migrations, crash recovery, artifact hashing, and V1 adapters.
- A fake OpenAI client runs a complete offline experiment in default CI.
- Live OpenAI smoke tests require explicit manual activation and never run in default CI.

Primary paired analysis includes only preregistered complete pairs, while reports retain every Execution and explicitly show missingness, Infrastructure Failures, Model Output Failures, exclusions, and bounded replacement executions. Incomplete or failed activity is never silently omitted.

Before any held-out execution, exactly one Experiment Manifest is preregistered for every Task and method arm being reported. Alternate Manifests remain visible as separate exploratory experiments; all preregistered held-out outcomes are reported, and no Manifest may be selected or suppressed after observing held-out results.

## Cost and secret safety

Validation occurs before any OpenAI request and reports maximum request, token, and episode-execution limits. Live execution requires explicit enablement and configured cost caps. Secrets never enter Manifests, the Attempt Store, Artifacts, or logs.

## Repository data policy

Runtime SQLite databases, model payloads, and execution artifacts are ignored by Git. Git contains migrations, Seed Suites, Experiment Specifications, prompt templates, and optionally small aggregate reports carrying their Experiment, Execution, and Memory Snapshot IDs.

Cross-machine transfer uses a versioned export bundle containing the Manifest, scoped Attempt Store records, Memory Snapshot, referenced Artifact hashes, and checksums. Import validates schemas, hashes, and stable IDs and rejects conflicting data rather than overwriting it.

Code identifiers, schemas, CLI help, the glossary, ADRs, and formal design documents use English canonical language. Collaboration may occur in Chinese; translated public documentation remains separate from canonical terminology.

## Licensing gate

Existing attribution is preserved. Before distributing V2, the project must verify the license and copyright obligations of the reused `prog_policies` implementation and add an appropriate top-level LICENSE and NOTICE. Until that review is complete, V2 assumes GPL-3.0-compatible distribution for linked or derived reuse and makes no claim that closed or differently licensed distribution is permitted.
