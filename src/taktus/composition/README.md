# Composition root

Where ports meet adapters — the only place that constructs an adapter and binds it to a port.
No business logic lives here, and this is the only package that may import everything.

`daemon.py` is `taktusd`: it reads and validates the settings (`settings.py`, one sentence
naming the variable when one is wrong), logs the effective configuration with every secret
masked (`logging.py`), connects to PostgreSQL — migrating on start when told to, refusing to
serve against a schema that is not at this build's revision — wires every port once, starts the
roles `TAKTUS_ROLES` names (`roles.py`: the runner over the queue port, the scheduler's
election over the leadership port, automation) and the HTTP surface, and on SIGTERM lets every
running step reach its boundary before it exits.

`local.py` wires `taktusctl` for a developer's machine: PostgreSQL when `TAKTUS_DATABASE_URL`
(or `_FILE`) is configured, otherwise the in-memory stores with a file snapshot under a state
directory; one HTTP worker, the system clock, no-op telemetry. Which one it chose is stated in
`Services.storage` and printed by `taktusctl run`. `taktusctl.py` is the console script.
