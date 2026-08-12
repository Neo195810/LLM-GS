# Calibrate and freeze request token limits

Pilot activity will estimate role-specific input and output limits that are sufficient for normal work while bounding cost, rather than seeking the model's maximum capacity. Limits cover the observed P99 with 20–30 percent output headroom and a capped input allowance; 80 percent usage triggers a recorded warning, while 100 percent triggers deterministic trimming and then blocks requests that still exceed the limit. These limits and rules are frozen in the Manifest before held-out evaluation and cannot be raised after observing results.
