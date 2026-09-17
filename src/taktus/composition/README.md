# Composition root

Where ports meet adapters. `local.py` wires a developer's machine: PostgreSQL when
`TAKTUS_DATABASE_URL` is configured (read through the configuration port; the schema revision is
checked before anything runs), otherwise the in-memory stores with a file snapshot under a state
directory; one HTTP worker, the system clock, no-op telemetry. Which one it chose is stated in
`Services.storage` and printed by `taktusctl run`. `taktusctl.py` is the console script: it
starts the command-line adapter with that wiring. No business logic lives here, and this is the
only package that may import everything.

`settings.py` is what `taktusd` is told about itself: every `TAKTUS_*` setting read through the
configuration port and validated once, so that a wrong one is refused with a sentence naming the
variable and never a stack trace. `logging.py` renders one JSON object per line and logs the
effective configuration at startup with every secret masked and its source named; a test proves
that no secret value reaches a line.
