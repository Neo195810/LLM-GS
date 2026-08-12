# Require deterministic V1 adapter equivalence

V2 adapters do not need to reproduce nondeterministic OpenAI outputs bit for bit, but a fixed DSL program executed with identical Task seeds and limits must match V1 in episode terminal state, reward, crash status, and program call count. An adapter cannot serve as a baseline until these deterministic equivalence tests pass.
