# LLM-GS V2: Experience Memory and Failure-Driven Repair

## Problem Statement

LLM-GS currently generates Candidate Programs and searches around them, but it does not retain successful and failed Program Attempts as reusable experience. When a Candidate Program fails, the agent generally regenerates or restarts instead of using Evaluation Evidence to diagnose the failure, preserve correct behavior, and repair the current program. This wastes Episode Evaluations and model requests, prevents learning across correction rounds and experiment runs, and makes it difficult to determine whether memory or explicit Reflection improves programmatic policy synthesis.

The current repository is also a research prototype rather than a recoverable experimental system. Model and prompt behavior are tightly coupled to V1, success is treated as a reward threshold, experiment identity and provenance are incomplete, failures from policies, model output, evaluation, and infrastructure are easily conflated, and there is no automated test suite. V2 needs to support controlled, reproducible comparisons without destroying the V1 baseline used for comparison.

## Solution

Build LLM-GS V2 as an executable, locally recoverable research platform that tests whether Experience Memory and evidence-linked Reflection improve the success rate and sample efficiency of programmatic policy synthesis.

V2 will preserve every immutable Program Attempt in an append-only Attempt Store and derive versioned Memory Snapshots through a deterministic Memory Curator. When a Candidate Program fails, one of four explicitly configured strategies—Regenerate, Reflect, Memory Repair, or Memory + Reflect—will determine whether the system starts over, diagnoses the current failure, retrieves prior experience, or combines both before repairing the same program through a bounded Repair Cycle.

Researchers will run versioned YAML Experiment Specifications through one validated `uv run llm-gs` CLI. Specifications resolve into immutable Experiment Manifests and IDs, and executions persist enough state to resume safely after interruption. V2 will use structured, versioned contracts for proposal, Diagnosis, repair, Episode Evaluation, memory retrieval, budgets, reports, and export bundles. The initial experiments will compare Hill Climbing, CEM, and CEBS on Karel and MiniGrid using paired Seed Suites, fixed Evaluation and Model Budgets, and a pinned OpenAI model. A gated TextWorld pilot will later test whether the design generalizes beyond the existing environments.

## User Stories

1. As a program-synthesis researcher, I want failed Candidate Programs to be diagnosed and repaired, so that useful partial behavior is not discarded after every failure.
2. As a program-synthesis researcher, I want successful and failed Program Attempts retained across correction rounds, so that later decisions can reuse prior evidence.
3. As a program-synthesis researcher, I want Experience Memory to persist across compatible experiment runs, so that I can measure cumulative learning.
4. As a program-synthesis researcher, I want raw Program Attempts separated from retrievable Memory Entries, so that changing memory policy does not rewrite experimental facts.
5. As a program-synthesis researcher, I want every Program Attempt to retain its parent and repair round, so that I can reconstruct the lineage of a repaired program.
6. As a program-synthesis researcher, I want each seeded execution represented as an Episode Evaluation, so that aggregate outcomes remain traceable to individual worlds.
7. As a program-synthesis researcher, I want Attempt Outcomes classified independently of scalar reward, so that success, partial completion, policy crashes, invalid programs, and evaluation errors are not conflated.
8. As a Task author, I want versioned Outcome Classifiers and Normalized Progress rules, so that each Task can express success and partial completion precisely.
9. As a program-synthesis researcher, I want shared Failure Types refined by Task-specific Failure Reasons, so that memory can be compared across Tasks without losing important details.
10. As a program-synthesis researcher, I want Diagnoses linked to concrete Evaluation Evidence, so that unsupported explanations cannot silently become memory.
11. As a program-synthesis researcher, I want a Repair Intent to state intended AST changes and preserved behavior, so that I can compare the intended and actual repair.
12. As a program-synthesis researcher, I want bounded Repair Cycles, so that one failing Candidate Program cannot consume the entire experiment budget.
13. As a program-synthesis researcher, I want a Repair Cycle to stop early on an unchanged AST, repeated failure, or no progress, so that futile repairs do not waste resources.
14. As a program-synthesis researcher, I want Regenerate, Reflect, Memory Repair, and Memory + Reflect available at the same post-failure intervention point, so that their effects can be compared cleanly.
15. As a program-synthesis researcher, I want the initial Proposer identical and memory-free across the primary ablation, so that initial proposal quality does not confound failure-handling results.
16. As a program-synthesis researcher, I want deterministic Structured Retrieval without embeddings in V2's first release, so that retrieval decisions are reproducible and explainable.
17. As a program-synthesis researcher, I want retrieval to hard-filter Experiment Context compatibility, so that raw experience is not used with an incompatible Task, DSL, environment, or model version.
18. As a program-synthesis researcher, I want memory ranked by Failure Type, Failure Reason, initial-state features, AST structure, evidence quality, repair improvement, and novelty, so that relevant examples are selected through visible criteria.
19. As a program-synthesis researcher, I want every retrieval candidate, component value, reason code, and selected Memory Entry recorded, so that retrieval behavior can be replayed and audited.
20. As a program-synthesis researcher, I want duplicate Memory Entries merged only under exact deterministic keys, so that approximate structural matches are not silently discarded.
21. As a program-synthesis researcher, I want Retrieval Outcomes recorded separately from Memory Entries, so that observed usefulness can be analyzed without mutating source experience.
22. As a program-synthesis researcher, I want Frozen Memory built from training seeds and read-only during held-out evaluation, so that I can measure generalization without leakage.
23. As a program-synthesis researcher, I want Online Memory reported as a distinct protocol, so that cumulative adaptation is not mixed with held-out generalization.
24. As a program-synthesis researcher, I want each online experimental arm and replicate to have an isolated Memory Lineage, so that treatments cannot contaminate each other.
25. As a program-synthesis researcher, I want primary algorithms to share the same balanced Frozen Memory Snapshot, so that memory quality is not confounded with search strategy.
26. As a program-synthesis researcher, I want Memory Entries to retain their source Search Strategy while remaining usable across algorithms, so that cross-search transfer can be measured.
27. As a program-synthesis researcher, I want versioned Seed Suites partitioned into memory-training, development, and held-out evaluation seeds, so that tuning and final evaluation remain isolated.
28. As a program-synthesis researcher, I want search and repair to finish before a unique final Candidate Program is evaluated on held-out seeds, so that held-out results cannot influence selection.
29. As a program-synthesis researcher, I want a deterministic final-candidate selection rule when no program fully succeeds, so that methods cannot choose favorable candidates after seeing results.
30. As a program-synthesis researcher, I want Evaluation Budget counted per Episode Evaluation, so that methods using more seeds cannot hide extra execution cost.
31. As a program-synthesis researcher, I want model requests, input tokens, and output tokens budgeted separately, so that lower environment cost cannot hide higher model cost.
32. As a program-synthesis researcher, I want submitted model requests counted even when their responses are unusable, so that reported cost reflects actual consumption.
33. As a program-synthesis researcher, I want infrastructure retries tracked separately from Repair Cycles, so that service failures are not learned as policy failures.
34. As a program-synthesis researcher, I want schema-invalid and DSL-invalid model output to follow a bounded correction path, so that formatting problems are visible and cannot retry indefinitely.
35. As a program-synthesis researcher, I want model-output exhaustion represented as Model Output Failure without creating a Program Attempt, so that invalid generation is not confused with policy execution.
36. As a program-synthesis researcher, I want role-specific token limits calibrated from pilot P99 behavior plus bounded headroom, so that prompts are sufficient without seeking unlimited context.
37. As a program-synthesis researcher, I want an 80-percent token warning and deterministic trimming at 100 percent, so that context pressure is observable and reproducible.
38. As a program-synthesis researcher, I want essential instructions, schemas, Task and DSL contracts, the current program, and minimum failure evidence protected from trimming, so that requests never silently lose their contract.
39. As a program-synthesis researcher, I want requests blocked when protected content still exceeds its limit, so that incomplete prompts are not submitted as valid experiments.
40. As a program-synthesis researcher, I want Memory Entries and evidence serialized as allowlisted data rather than concatenated historical instructions, so that prior content cannot become an uncontrolled instruction channel.
41. As a program-synthesis researcher, I want complete trajectory retention to be selective, so that storage remains bounded while important failures, successes, repair pairs, and deterministic samples remain inspectable.
42. As a program-synthesis researcher, I want seeds, versioned state features, Execution Summaries, and bounded failure windows retained for every attempt, so that behavior can be replayed without storing every full trajectory.
43. As a program-synthesis researcher, I want Experiment Specifications validated before any OpenAI call, so that invalid setup cannot incur model cost.
44. As a program-synthesis researcher, I want a resolved Experiment Manifest to include code, dependency, component, prompt, parser, model, seed, budget, and Memory Snapshot identity, so that an experiment is reproducible.
45. As a program-synthesis researcher, I want Experiment IDs derived from Manifests rather than display names, so that semantically different experiments cannot collide.
46. As a program-synthesis researcher, I want separate Execution IDs for repeated attempts of the same Manifest, so that infrastructure replacement runs remain visible.
47. As a program-synthesis researcher, I want persisted idempotent Work Units, so that interrupted executions can return incomplete work to pending without duplicating completed results.
48. As a program-synthesis researcher, I want completed evaluations to consume budget transactionally, so that crashes cannot overcount or undercount work.
49. As a program-synthesis researcher, I want submitted model costs retained even when result persistence is interrupted, so that recovery does not underreport spending.
50. As a program-synthesis researcher, I want one CLI for validation, run, resume, memory construction, held-out evaluation, reporting, and attempt inspection, so that the workflow is executable without custom scripts.
51. As a program-synthesis researcher, I want reports to show success rate under fixed budget as the primary metric, so that the central hypothesis has one preregistered outcome.
52. As a program-synthesis researcher, I want reports to include time-to-success, model usage, wall-clock time, Repair Cycle effectiveness, retrieval impact, and outcome distributions, so that trade-offs remain visible.
53. As a program-synthesis researcher, I want paired analyses to show all missing executions and infrastructure or model-output failures, so that unsuccessful activity is never silently excluded.
54. As a program-synthesis researcher, I want Frozen Memory and Online Memory results reported separately, so that incompatible evaluation meanings are not combined.
55. As a program-synthesis researcher, I want Experiment data exported as a self-verifying bundle, so that I can reproduce or audit it on another machine.
56. As a program-synthesis researcher, I want imports to validate schemas, IDs, Artifact hashes, and checksums and reject conflicts, so that evidence is not overwritten or corrupted.
57. As a maintainer, I want runtime databases, model payloads, and large trajectories excluded from Git, so that the repository contains durable specifications rather than execution data.
58. As a maintainer, I want V2 to run under Python 3.11 with `uv`, so that one locked modern environment replaces the inconsistent V1 Conda and pip setup.
59. As a maintainer, I want V2 to call the official OpenAI SDK directly, so that Structured Outputs, retries, request parameters, and usage accounting remain explicit.
60. As a maintainer, I want `gpt-5.6-luna` with reasoning effort `medium` pinned for initial experiments, so that model variation does not confound the primary comparison.
61. As a maintainer, I want proposal, Diagnosis, and repair to use separate version-controlled prompt templates with fixed hashes, so that role behavior is explicit and reproducible.
62. As a maintainer, I want model changes to require a recorded user decision based only on development evidence, so that held-out results do not drive model selection.
63. As a maintainer, I want model-generated programs accepted only through the project DSL and parsed AST, so that arbitrary Python cannot bypass evaluation constraints.
64. As a maintainer, I want V2 isolated from V1 behind adapters, so that the baseline remains executable during redesign.
65. As a maintainer, I want deterministic V1 adapter equivalence for fixed DSL programs and seeds, so that adapter-based baseline results are trustworthy.
66. As a maintainer, I want replaceable Proposer, Evaluator, Experience Memory, Reflector/Repairer, and Search Strategy contracts, so that controlled component experiments do not depend on orchestrator internals.
67. As a maintainer, I want Karel and MiniGrid retained in the initial benchmark, so that V2 remains comparable with V1.
68. As a maintainer, I want CleanHouse, FourCorners, DoorKey, and RedBlueDoor as the initial Task suite, so that the first comparison spans cleaning, coverage, object interaction, and ordering constraints.
69. As a maintainer, I want Hill Climbing, CEM, and CEBS compared using the same budgets and seeds, so that memory and Reflection can be tested across different Search Strategies.
70. As a maintainer, I want a constrained TextWorld pilot after the initial vertical slices, so that language grounding and object reasoning can test V2's generality without replacing the baseline.
71. As a maintainer, I want TextWorld gated by installation, licensing, replay, evidence, and performance checks, so that a newer environment is not assumed to be a better benchmark.
72. As a maintainer, I want automated offline experiments to use a fake OpenAI client, so that default CI never incurs API cost.
73. As a maintainer, I want live OpenAI smoke tests to require explicit manual activation and cost limits, so that tests cannot spend money unexpectedly.
74. As a maintainer, I want release blocked until reused V1 code licensing and attribution are clarified, so that V2 is not distributed under an unsupported licensing assumption.

## Implementation Decisions

- V2 is a separate Python package that may break V1 internals and configuration formats. V1 remains a read-only executable baseline and is reused only through adapters.
- Python 3.11, `uv`, modern package metadata, and a committed lockfile are the authoritative V2 runtime. Legacy Conda and requirements metadata remain transitional V1 inputs only.
- The platform is local, recoverable, and bounded in parallelism. Distributed scheduling, shared database services, and multi-user authorization are not required initially.
- One validated CLI exposes `run`, `resume`, `memory build`, `evaluate`, `report`, `inspect attempt`, and `validate` operations.
- Users author versioned YAML Experiment Specifications. Strict schema validation resolves every explicit and default value into an immutable Experiment Manifest, from which the Experiment ID is derived.
- One workspace-level migrated SQLite database in WAL mode stores structured records. Large content is stored as content-addressed Artifacts referenced by hashes.
- Program Attempts and related provenance are append-only. Later analysis creates derived records and never rewrites historical facts.
- One Program Attempt aggregates one or more Episode Evaluations. Evaluation Budget is counted per episode, while reports also expose candidate evaluation counts.
- Persisted Work Units use idempotency keys and move through pending, running, and terminal states. Interrupted running work returns to pending; completed evaluation and budget accounting commit atomically.
- Attempt Outcomes are Success, Partial Completion, Policy Crash, Invalid Program, or Evaluation Error. Infrastructure Failure and Model Output Failure are Work Unit outcomes rather than policy outcomes.
- Each Task owns a versioned Outcome Classifier, Normalized Progress definition, and Failure Reasons under a shared Failure Type taxonomy.
- Every Evaluation produces an Execution Summary. Full Execution Artifacts are retained selectively according to deterministic policy and capacity.
- The initial Repair Cycle limit is three repaired descendants per failed Candidate Program, configurable and available for 0/1/3 ablation for strategies that retain and repair that candidate. Regenerate does not enter a Repair Cycle and returns directly to Global Search. Comparisons across all four strategies are aligned by identical total Evaluation and Model Budgets and paired seeds, not by forcing Regenerate to perform synthetic repair steps. Repeated AST, repeated failure without improvement, and budget exhaustion stop a Repair Cycle early.
- Proposer, Evaluator, Experience Memory, Reflector/Repairer, and Search Strategy use small versioned typed contracts and registry names. Plugins cannot access orchestrator internals.
- Proposal, Diagnosis, and repair call the official OpenAI Responses API with versioned Structured Output schemas. DSL source is a structured field and must also pass the local parser.
- V2 supports OpenAI only. Initial experiments pin `gpt-5.6-luna`, reasoning effort `medium`, fixed role-specific prompts, fixed sampling parameters, and fixed role-specific output limits.
- A logical model request may make at most two format-correction requests using only validation errors and the original output. Every physical request consumes Model Budget.
- Prompt and parser hashes, all actual request parameters, finish reasons, usage, and cached-token counts are retained. Secrets are never persisted.
- Request Token Limits are calibrated before held-out evaluation. An empirical P99 requires at least 100 valid development responses per role; insufficient samples use a provisional observed maximum plus 30 percent and block held-out execution.
- Output limits cover normal P99 plus 20–30 percent headroom. Input limits cover the normal prompt, allowed memory, and allowed evidence P99 under an explicit cost ceiling.
- At 80 percent token use, the system records a warning. At 100 percent, deterministic Context Trimming runs and records every removal; requests that still exceed limits are blocked.
- Context Trimming protects the system instructions, response schema, Task and DSL contracts, current Candidate Program, and minimum failure evidence. It removes low-ranked optional Memory Entries, shortens noncritical evidence windows, and removes representative successes before similar failures and effective repair pairs.
- Experience Memory is a versioned, rebuildable retrieval view over the Attempt Store. A deterministic Memory Curator retains new failures, representative successes, effective repair pairs, and source frequencies while merging only exact duplicate keys.
- V2 initially uses Structured Retrieval without embeddings. Compatibility filtering precedes Failure Type/Reason buckets, deterministic state and AST feature ranking, and explicit tie-breaking. The retriever's full ordering or weights and version are fixed on development seeds, recorded in the Experiment Manifest, and frozen before building a held-out Memory Snapshot.
- Memory and evidence use allowlisted versioned serializers with fixed data boundaries. Historical free text is never concatenated into instruction space.
- Frozen Memory is produced before evaluation and remains read-only. Online Memory updates only at stable decision boundaries and is sequential initially.
- Every online method, algorithm, and replicate forks an isolated Memory Lineage from the same starting Snapshot. Formal Frozen comparisons share a balanced independently generated Snapshot.
- Initial Proposers never consume Experience Memory in the main ablation. Memory intervention occurs only after failure.
- The primary failure-handling strategies are Regenerate, Reflect, Memory Repair, and Memory + Reflect. V1 behavior and the V2 adapter control remain separate system baselines.
- Karel CleanHouse and FourCorners and MiniGrid DoorKey and RedBlueDoor form the initial Task suite. Hill Climbing, CEM, and CEBS form the initial Search Strategy suite.
- Seed Suites separate memory-training, development, and held-out evaluation. Search, Diagnosis, and Repair never observe held-out evidence.
- Exactly one final Candidate Program is selected before held-out evaluation using this lexicographic order: Attempt Outcome, search-seed success proportion, mean Normalized Progress, worst-seed Normalized Progress, lower episode cost, then stable identity.
- The primary metric is held-out Task success rate under fixed Evaluation Budget. Secondary metrics cover time-to-success, requests, tokens, wall-clock time, Repair Cycle effectiveness, retrieval impact, and outcome distributions.
- Replicates use paired Task seeds, search RNG seeds, model settings, and budgets. Replicate counts and confidence interval methods are fixed from pilot variance before formal evaluation. Exactly one Experiment Manifest per Task and method arm is preregistered for held-out evaluation; every preregistered outcome is reported, while alternate Manifests remain explicitly exploratory and cannot replace or suppress a result after it is observed.
- Infrastructure Retry limits and backoff rules are part of the Experiment Manifest. Exhaustion produces an Infrastructure Failure Work Unit outcome, creates no failed Program Attempt, consumes no additional Episode Evaluation beyond work already completed transactionally, and remains visible in failure and missingness reports.
- Formal executions prohibit human changes. Any semantic correction creates a new Manifest and Execution; interactive development data cannot enter the primary Frozen Snapshot or held-out report.
- Application-level replay of OpenAI responses is prohibited in formal experiments. Provider prompt caching is allowed and reported. Offline tests use fake or recorded responses.
- Export bundles contain scoped records, Manifests, Memory Snapshots, referenced Artifact hashes, and checksums. Imports validate identity and reject conflicts rather than overwrite evidence.
- Runtime data is ignored by Git. Durable schemas, migrations, Seed Suites, Experiment Specifications, prompts, and small provenance-bearing reports may be committed.
- Karel and MiniGrid remain the initial environments. A constrained TextWorld pilot follows the initial slices and must pass Python 3.11, license, 100-seed cross-process replay, structured evidence, and measured performance gates before formal inclusion.
- Distribution is gated on resolving the GPL-3.0 attribution and licensing boundary of reused V1 components and adding suitable license and notice material.
- Delivery proceeds as executable vertical slices: platform/storage/fake model; CleanHouse plus Hill Climbing with Regenerate and Reflect; memory and the remaining failure strategies; protocols/recovery/reporting; remaining initial Tasks; then CEM, CEBS, and the full ablation.

## Testing Decisions

- The primary test seam is the highest external behavior boundary: a valid Experiment Specification executed through the CLI with a fake OpenAI client must create a recoverable Execution, persist inspectable Program Attempts and Memory provenance, respect all budgets, and produce a deterministic Report. Most behavior should be proven through this seam rather than through internal call assertions.
- A second high-value seam verifies V1 adapter equivalence. Given a fixed DSL program, identical Task seeds, and identical limits, V1 and the adapter must produce the same terminal state, reward, crash status, and program call count. Nondeterministic model text is outside this equivalence test.
- Storage integration tests cover migrations, WAL-backed transactions, append-only records, Artifact hashes, idempotent Work Units, crash recovery, atomic budget accounting, export/import verification, and conflict rejection.
- Model-boundary contract tests use fake Responses API payloads to cover schema-valid output, schema errors, DSL parser errors, output-length termination, two bounded corrections, usage accounting, retry classification, and secret redaction.
- Golden tests cover complete serialized proposal, Diagnosis, repair, memory-context, evidence-context, and report payloads for fixed examples. Golden updates require intentional review because serializer changes alter Experiment identity.
- Task-level behavior tests cover each Outcome Classifier, Normalized Progress, Failure Type/Reason mapping, deterministic State Feature Extractor, Execution Summary, and failure-window selection.
- Property-based tests cover schema round trips, stable Manifest and Artifact hashing, append-only Attempt Store invariants, idempotency, budget non-exceedance, deterministic Context Trimming, exact duplicate curation, and stable retrieval ordering.
- Retrieval behavior tests verify hard compatibility filters, exact bucket selection, AST and state-feature component values, tie-break order, category quotas, and complete reason-code provenance without asserting private implementation structure.
- Repair behavior tests verify parent-child links, Diagnosis evidence citations, hypothesis labeling, preserved behavior in Repair Intent, actual AST diffs, early stopping, and the configured 0/1/3 limits.
- Protocol tests prove that Frozen Memory cannot mutate during evaluation, Online Memory updates only at stable boundaries, lineages cannot cross arms or replicates, and held-out evidence cannot flow back into search or memory.
- Reporting tests prove complete paired accounting, explicit missingness, infrastructure and model-output failure rates, exclusion and replacement rules, and separation of Frozen and Online results.
- Cost tests prove request, input-token, output-token, Episode Evaluation, and currency safety limits; 80-percent warnings; 100-percent trimming; and blocking when protected minimum content cannot fit.
- A manual live OpenAI smoke test verifies the pinned model, reasoning effort, Structured Outputs, usage fields, and credentials without becoming part of default CI.
- TextWorld is tested only as a gated pilot: clean Python 3.11 installation and license inventory, 100 seeds replayed across two processes, terminal/evidence/score/action equality, required evidence categories, p50/p95 runtime and memory, trace size, and oracle/failure/equivalent-policy adapter checks.
- The current repository has no prior automated test suite. V1 experiment scripts are prior behavioral evidence, not reusable test infrastructure; V2 establishes the above seams from scratch while preserving V1 adapter equivalence.

## Out of Scope

- Replacing Karel or MiniGrid in the initial benchmark.
- Embedding or semantic-vector retrieval in the first V2 release.
- Memory-augmented initial proposal in the primary ablation.
- Proving semantic equivalence between different program ASTs.
- Executing arbitrary model-generated Python in V2 experiments.
- Supporting non-OpenAI model providers.
- Dynamically selecting different models for roles or Tasks in the primary experiment.
- Distributed multi-node scheduling, shared database services, or multi-user authorization.
- A Web UI or hosted service.
- A stable third-party environment extension API before a real third-environment integration validates the contracts.
- Automatic parallel Online Memory updates without deterministic batch Snapshot semantics.
- Using held-out results to tune prompts, budgets, retrievers, curators, models, or final-candidate selection.
- Silently excluding failed or incomplete executions from reports.
- Automatically deleting referenced Artifacts.
- Committing runtime databases, full model payloads, or large trajectories to Git.
- Claiming closed-source or non-GPL-compatible distribution before the V1 licensing boundary is reviewed.
- Making Craftax, HighwayEnv, pyRDDLGym, OpenSpiel, NLE, or other environments part of the initial formal benchmark.
- Treating TextWorld as a formal benchmark before its acceptance gates pass.

## Further Notes

- The specification is governed by the project's canonical glossary and accepted ADRs. Domain terms in this issue intentionally match those definitions.
- The central research claim is not that V2 must outperform V1 to be considered implemented. Completion means the platform executes controlled, recoverable, attributable experiments; whether memory and Reflection improve results is an empirical outcome.
- Formal held-out experiments begin only after pilot budgets, token limits, replicate counts, confidence intervals, exclusions, replacement rules, prompts, schemas, and component versions are frozen.
- The design favors explainable and deterministic mechanisms first. Embeddings, parallel Online Memory, alternate models, and additional environments should enter later as explicit comparative experiments rather than silent upgrades.
- The accepted implementation order is intentionally vertical: every milestone must end in an executable experiment with automated acceptance checks.
