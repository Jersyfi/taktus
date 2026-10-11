# Exactness tests

An `exact` step never takes its final value from a variable method (ADR-0014, ADR-0018), held on
three levels: the model (the shared kernel's `Step` and the process domain each refuse it, and a
process version containing such a step does not exist), the example bundles under
`examples/processes/` (every one loads, and no exact step is on a method outside `rule` and
`statistics`), and execution (an exact step runs as a rule of the run component, never through an
adapter). A step that is classed exact and reads a worker's artifact does so through a machine
check, which is the pattern of ADR-0014 §4.1.

The backlog's ready standard is held the same way: P-03's admission and P-02's search for the
sections an issue lacks are `rule` steps classed `exact` that run the rule `ready` (issue #70).

`test_exactness_statement.py` holds the first part of UC-4.13 and UC-6.9 (#91, ADR-0082). An
`exact` step without a check from the catalogue does not register, and the finding names every
row. Every example and blueprint bundle's statement renders with all four parts, and names
every result-producing step. A changed check changes the statement. A statement without what its
checks do not cover, or one that says "guaranteed", is refused. Every sentence about a check is
its row's, filled in with that check's parameters and nothing else: varying one parameter
changes exactly its place in every sentence. Running the checks is #223.
