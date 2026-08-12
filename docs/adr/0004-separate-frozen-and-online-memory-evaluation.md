# Separate frozen and online memory evaluation

V2 will treat held-out generalization and cumulative adaptation as different experiment protocols. Frozen Memory is built only from training seeds and remains read-only during evaluation; Online Memory may learn from earlier evaluation attempts, but its results are reported separately and never mixed into the primary Frozen Memory comparison.
