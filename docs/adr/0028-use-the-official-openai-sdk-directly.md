# Use the official OpenAI SDK directly

V2 will use the official OpenAI Python SDK and Responses API directly for Structured Outputs, explicit retries, request parameters, and usage accounting. LangChain remains only in the V1 baseline, avoiding hidden parameter conversion or retry behavior in experiments whose request and token costs must be attributable.
