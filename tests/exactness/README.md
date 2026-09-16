# Exactness tests

An `exact` step never takes its final value from a variable method (ADR-0014, ADR-0018), held on
three levels: the model (the shared kernel's `Step` and the process domain each refuse it, and a
process version containing such a step does not exist), the example bundles under
`examples/processes/` (every one loads, and no exact step is on a method outside `rule` and
`statistics`), and execution (an exact step runs as a rule of the run component, never through an
adapter). A step that is classed exact and reads a worker's artifact does so through a machine
check, which is the pattern of ADR-0014 §4.1.
