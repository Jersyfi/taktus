# Composition root

Where ports meet adapters — the only place that constructs an adapter and binds it to a port.
No business logic lives here, and this is the only package that may import everything.

`daemon.py` is `taktusd`: it reads and validates the settings (`settings.py`, one sentence
naming the variable when one is wrong), logs the effective configuration with every secret
masked (`logging.py`), connects to PostgreSQL — migrating on start when told to, refusing to
serve against a schema that is not at this build's revision — wires every port once, starts the
roles `TAKTUS_ROLES` names (`roles.py`: the runner over the queue port, the scheduler's
election over the leadership port, automation) and the HTTP surface, and on SIGTERM lets every
running step reach its boundary before it exits. While the scheduler leads it fires the time
triggers that are due (`triggers.py`, ADR-0035): a firing crosses the process, command and run
components, so it is wired here. While the automation role leads it reacts to the events the
intake kept (`reactions.py`, ADR-0048), across the same three components. The identity component
places every sender; a sender it cannot
place is answered in the channel through the reply operation of the channel's connector
(`replies.py`, ADR-0040), which the connector pool resolves, so that is wired here too. What is
needed from the owner reaches them through the same reply operation, and their answer in a
report's thread comes back through the intake (`owner_channel.py`, ADR-0045): the reporting
component keeps the report, the decision component files a decision answer, and a decision
confirmed there hands its run on. A request for a run or a process in the owner's conversation
comes back the same way and is answered with the level's text equivalent and a link to it in
the web app, read through the levels the `api` role serves (ADR-0069). The phrasebooks Taktus ships, one per language, are
`phrasebooks/*.json`: the core names no language. While it leads, the scheduler also looks for a
broken interface in the run's failed calls and reports it to the owner through the same channel
(`interfaces.py`, ADR-0047). The guides' process, S-05, asks the instance through the loopback
connector to render, measure and publish the guides and to report a hand edit; `guides.py`
answers over the knowledge and reporting components, and serves `knowledge.pages` over the
directory `TAKTUS_KNOWLEDGE_DIRECTORY` names (ADR-0066).

`local.py` wires `taktusctl` for a developer's machine: PostgreSQL when `TAKTUS_DATABASE_URL`
(or `_FILE`) is configured, otherwise the in-memory stores with a file snapshot under a state
directory; one HTTP worker, the system clock, no-op telemetry. Which one it chose is stated in
`Services.storage` and printed by `taktusctl run`. `taktusctl.py` is the console script.

`conformance.py` is the instance running an adapter's conformance suite itself: the catalog's
`Suites` port over `taktus.conformance`, against the endpoint the configuration resolves for an
adapter identifier (ADR-0044). Both `local.py` and `daemon.py` wire it to the catalog's one writer
and to the loopback. `pools.py` holds the three pools the engine resolves from and reads what
stands behind an identifier — the same reading for a removal verdict, a conformance pass and the
maturity a run asks for (`maturity.py`).
