# Use uv and local recoverable execution

V2 will use `uv` as its only supported Python environment and command entry point, replacing V1's Conda-oriented setup. The first release targets single-machine, recoverable execution with bounded local parallelism; its component contracts should not require one process, but distributed scheduling and multi-node storage are outside the initial scope.
