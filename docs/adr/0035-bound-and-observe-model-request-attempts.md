# Bound and observe model request attempts

Every Model Request Attempt will time out after 60 seconds. A timeout or retryable provider failure receives at most one Request Retry, so the same logical request has at most two attempts. Only after those attempts fail may the existing Matrix Arm Infrastructure Retry policy repeat the wider operation.

The runtime records each attempt's duration, terminal result or exception type, and retry layer. This distinguishes a valid model response, bounded output correction, Request Retry, and Matrix Arm Infrastructure Retry. A timed-out submission may already have reached the provider, so its Cost Reservation remains Unknown Usage until reconciled.

## Consequences

The official SDK's implicit retries must not hide individual attempts from experiment records; the implementation will disable them and make the retry boundary observable. Each provider submission counts against Model Budget, so a Candidate Program reserves up to six submissions: three bounded output-correction calls, each with up to one Request Retry. A Matrix Arm can still be recovered under its existing policy, but reports can identify whether elapsed time came from provider latency, individual request retries, or repeated arm execution. The 60-second limit intentionally favors timely recovery over accepting unusually slow responses; its rate and latency distribution must be observed before changing it.
