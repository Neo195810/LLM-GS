# Compose V2 from replaceable research roles

LLM-GS V2 will execute experiments by composing replaceable Proposer, Evaluator, Experience Memory, Reflector/Repairer, and Search Strategy roles. This makes controlled ablations and comparisons possible without turning V2 into a general-purpose platform; the existing Environment, Task, and DSL abstractions remain unless they block one of these roles.

Every Candidate Program execution consumes Evaluation Budget, while model requests and tokens consume a separately reported Model Budget. Infrastructure retries are bounded and tracked separately so policy failures and system failures cannot be conflated.
