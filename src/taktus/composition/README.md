# Composition root

Where ports meet adapters. `local.py` wires a developer's machine: the in-memory stores with a
file snapshot under a state directory, one HTTP worker, the system clock, no-op telemetry.
`taktusctl.py` is the console script: it starts the command-line adapter with that wiring. No
business logic lives here, and this is the only package that may import everything.
