# LLM-GS V2

LLM-GS V2 explores whether retained experience and failure-driven correction improve the synthesis of programmatic reinforcement-learning policies.

## Language

**Candidate Program**:
A program proposed as a possible policy for a Task and awaiting or undergoing evaluation.
_Avoid_: Solution, answer

**Program Attempt**:
A Candidate Program together with the Experiment Context, evaluation outcome, and evidence produced by evaluating it.
_Avoid_: Trial, sample, run

**Episode Evaluation**:
The execution and result of one Candidate Program in one seeded initial world; multiple Episode Evaluations are aggregated into one Program Attempt.
_Avoid_: Program Attempt, episode

**Attempt Outcome**:
The domain classification of a Program Attempt as Success, Partial Completion, Policy Crash, Invalid Program, or Evaluation Error. Each Task defines its own success condition; failures outside the policy are Evaluation Errors.
_Avoid_: Boolean result, pass/fail

**Outcome Classifier**:
The versioned Task-specific rules that classify Episode Evaluations and their aggregate Program Attempt independently of reward magnitude.
_Avoid_: Reward threshold, success flag

**Normalized Progress**:
A Task-specific value defined with the Outcome Classifier that expresses partial goal completion on a comparable zero-to-one scale within that Task.
_Avoid_: Reward, success probability

**Failure Type**:
A cross-Task classification of unsuccessful policy behavior, refined by a Task-specific Failure Reason without changing its shared meaning.
_Avoid_: Error message, Attempt Outcome

**Failure Reason**:
A Task-specific explanation nested under a Failure Type, such as leaving markers uncollected or opening doors in the wrong order.
_Avoid_: Failure Type, Diagnosis

**Evaluation Evidence**:
Structured observations from evaluating a Candidate Program that support its Attempt Outcome and any subsequent Reflection.
_Avoid_: Log, feedback

**Execution Summary**:
The always-retained structured account of a Candidate Program's behavior, including its outcome and a bounded window around each relevant failure point.
_Avoid_: Trace, transcript

**Execution Artifact**:
An optionally retained full execution trajectory used for replay, diagnosis, or auditing; it is not required for every Program Attempt.
_Avoid_: Execution Summary, memory

**Artifact**:
Content-addressed experiment material stored outside structured records and referenced by its content hash.
_Avoid_: Result, attachment

**Experiment Context**:
The combination of environment family, Task, DSL, and model version that determines where a Program Attempt's experience is directly applicable.
_Avoid_: Configuration, setup

**Experience Memory**:
The persistent collection of successful and failed Program Attempts available across correction rounds and experiment runs within the same Experiment Context.
_Avoid_: History, cache, database

**Attempt Store**:
The append-only source of truth containing every immutable Program Attempt and its provenance, independent of whether that attempt is selected for retrieval.
_Avoid_: Experience Memory, result directory

**Memory Entry**:
A versioned, rebuildable representation selected or derived from the Attempt Store for retrieval by a Reflector/Repairer or Proposer.
_Avoid_: Program Attempt, record

**Memory Curator**:
The role that selects, deduplicates, or derives Memory Entries from Program Attempts without changing the Attempt Store.
_Avoid_: Filter, cleanup job

**Structured Retrieval**:
Retrieval based only on explicit fields such as Experiment Context, failure type, AST structure, initial-state features, and measured repair improvement.
_Avoid_: Semantic search, embedding search

**State Feature Extractor**:
The deterministic, versioned environment-family role that converts an initial world into explicit structural features for retrieval and analysis.
_Avoid_: Embedding, map description

**Reflection**:
The process that examines Evaluation Evidence and, when permitted, relevant Experience Memory to produce a persistent Diagnosis.
_Avoid_: Retry, critique

**Repair Cycle**:
A bounded sequence that reflects on a failed Candidate Program, repairs that same program, and evaluates it again before returning control to Global Search.
_Avoid_: Retry loop, revision

**Global Search**:
The process that explores alternative Candidate Programs after a Repair Cycle succeeds or exhausts its correction budget.
_Avoid_: Restart, regeneration

**Abstract Experience**:
Experience distilled from Program Attempts for possible use outside their original Task; unlike raw attempts, it contains no task-specific program or evaluation details.
_Avoid_: Shared memory, transferable case

## Experimentation

**Frozen Memory Protocol**:
An evaluation protocol in which Experience Memory is built only from designated training seeds and remains read-only while evaluation seeds run.
_Avoid_: Offline mode, static memory

**Online Memory Protocol**:
An evaluation protocol in which Program Attempts from earlier evaluation activity may become available to later activity, measuring cumulative adaptation rather than held-out generalization.
_Avoid_: Live mode, normal evaluation

**Experiment Manifest**:
The immutable, fully resolved description of an experiment, including code and dependency state, component versions, model parameters, seeds, budgets, and Memory Snapshot.
_Avoid_: Config, experiment name

**Experiment Specification**:
The versioned, user-authored YAML input that is validated and fully resolved into an Experiment Manifest.
_Avoid_: Experiment Manifest, CLI arguments

**Experiment ID**:
The identity derived from an Experiment Manifest; display names are aliases and do not determine experimental identity.
_Avoid_: Run name, output name

**Execution ID**:
The identity of one execution of an Experiment Manifest, including executions repeated after infrastructure failure.
_Avoid_: Experiment ID, run name

**Memory Snapshot**:
A fixed, identified version of Experience Memory used by an experiment or an evaluation boundary.
_Avoid_: Memory version, checkpoint

**Memory Lineage**:
The ordered ancestry of Memory Snapshots forked from a common starting Snapshot and updated within one isolated experimental arm.
_Avoid_: Experiment history, database branch

**Memory Context Budget**:
The fixed limits on the number and serialized token size of Memory Entries supplied to a model request.
_Avoid_: Context window, Model Budget

**Evidence Context Budget**:
The fixed limit on serialized Episode Evaluation evidence supplied to a Diagnosis request.
_Avoid_: Memory Context Budget, Model Budget

**Seed Suite**:
A versioned partition of seeded initial worlds into memory-training, development, and held-out evaluation groups for a Task.
_Avoid_: Seed list, dataset split

**Evaluation Budget**:
The maximum number of Episode Evaluations permitted in an experiment, including executions performed during Repair Cycles.
_Avoid_: Program budget, iteration limit

**Model Budget**:
The separately tracked limits on model requests and consumed tokens; every submitted request counts even if its response is unusable.
_Avoid_: Retry budget, LLM budget

**Request Token Limit**:
A role-specific hard limit on serialized input or generated output, calibrated before held-out evaluation from normal pilot behavior and fixed in the Experiment Manifest.
_Avoid_: Model context window, Model Budget

**Context Trimming**:
The deterministic, versioned removal of optional Memory Entries or Evaluation Evidence when a serialized request reaches its Request Token Limit.
_Avoid_: Summarization, truncation

**Infrastructure Retry**:
A bounded repeat of an operation that failed for reasons outside the Candidate Program, such as temporary service unavailability. It does not create a failed Program Attempt.
_Avoid_: Repair, regeneration

**Infrastructure Failure**:
A terminal Work Unit outcome caused by an external or execution-system failure after Infrastructure Retries are exhausted; it is reported separately from policy outcomes.
_Avoid_: Policy Crash, Evaluation Error

**Model Output Failure**:
A terminal Work Unit outcome produced when bounded format-correction attempts cannot yield schema-valid and DSL-valid model output; it does not create a Program Attempt.
_Avoid_: Invalid Program, Infrastructure Failure

**Work Unit**:
An idempotently identified, persistently tracked piece of experiment work that moves through pending, running, and terminal states.
_Avoid_: Job, iteration

**Matrix Arm**:
One preregistered Task, Search Strategy, Failure Handling Strategy, protocol, and replicate combination in an Ablation Matrix. A Matrix Arm owns its lifecycle and may have multiple Executions when recovery is permitted.
_Avoid_: Experiment, Work Unit

**Matrix Arm State**:
The durable state of a Matrix Arm: pending, running, completed, model-output-failed, infrastructure-failed, or blocked-by-budget. Completed means its Execution reached an experiment result; it does not imply policy success.
_Avoid_: Missing, pass/fail

**Correction Feedback**:
The bounded, structured description supplied to a self-contained model correction or repair request: relevant prior output, validation or evaluation evidence, and the protected Task and DSL contract. It does not rely on implicit API conversation state.
_Avoid_: Conversation history, raw error log

**Invalid-output Artifact**:
A private, bounded, redacted record of an invalid model output, its correction prompt, and validation evidence, retained for diagnosis without changing failure classification.
_Avoid_: Execution Artifact, Failure Reason

## Platform Roles

**Proposer**:
The role that produces initial Candidate Programs.

**Evaluator**:
The role that executes Candidate Programs and returns their Attempt Outcomes with Evaluation Evidence.

**Reflector/Repairer**:
The role that diagnoses a failed Program Attempt using relevant Experience Memory and produces a corrected Candidate Program in the same Repair Cycle.

**Diagnosis**:
The persistent, evidence-linked output of Reflection that explains a failed Candidate Program and states the correction direction passed to repair.
_Avoid_: Feedback, chain of thought

**Repair Intent**:
The structured description of which AST regions a repair is intended to change, why they should change, and which correct behavior must remain intact.
_Avoid_: Patch, Diagnosis

**Retrieval Outcome**:
An immutable observation of how a retrieved Memory Entry was used and whether the subsequent attempt improved, changed failure type, or succeeded.
_Avoid_: Memory Entry score, feedback

## Failure Handling Strategies

**Regenerate**:
Discard the failed candidate and request a new Candidate Program without Diagnosis or Experience Memory.

**Reflect**:
Diagnose and repair the failed candidate using only its current Evaluation Evidence.

**Memory Repair**:
Repair the failed candidate using retrieved Memory Entries without first producing an explicit Diagnosis.

**Memory + Reflect**:
Diagnose and repair the failed candidate using both its current Evaluation Evidence and retrieved Memory Entries.

**Search Strategy**:
The role that chooses which Candidate Program the Global Search explores next.
_Avoid_: Search algorithm

**Normalized AST**:
The canonical syntax-tree representation used to compare program structure after removing formatting and other meaningless surface differences; it does not claim semantic equivalence.
_Avoid_: Equivalent program, canonical program
