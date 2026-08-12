# Compose plugins through versioned small contracts

Replaceable V2 research roles will implement small Python typed Protocols with versioned input and output models and will be composed through explicit registry names in configuration. Plugins cannot depend on orchestrator internals, and V1 behavior enters through adapters, avoiding both a deep inheritance hierarchy and compatibility logic inside the V2 core.
