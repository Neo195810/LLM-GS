# Use structured OpenAI output contracts

V2 will call the OpenAI Responses API with versioned Structured Output schemas for proposal, Diagnosis, and repair. DSL source remains a schema field and must also pass the local DSL parser; schema-invalid responses consume Model Budget and may receive bounded format correction, but do not create Program Attempts until a valid Candidate Program exists.
