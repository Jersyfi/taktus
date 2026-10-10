"""Owns the reader's side: views and who may see them, reports and when they are delivered to
whom, and the explanation of an action given on request (ADR-0029). It owns no figure: every
number it shows is read from the component that produces it.

What exists today:

- the product finding (UC-6.12, ADR-0046): what an instance met that the product lacks — a
  capability no configured adapter offers, an operation a connector does not support. A rule
  reads it from the run's blocked-time accounts (`domain/service/findings.py`). The findings
  are grouped by the lack and written in the shape of the issue form `Task`
  (`domain/service/texts.py`). They are shown to the operator, and sent to the Taktus
  repository where the operator enabled it (`application/service/product_findings.py`). The
  blocks and their durations are the run's; the channel a finding is sent through is a port
  (`ports/findings.py`) that the composition root binds to a connector.

A finding names no person (principle 14): its values have no field that can hold one.

The owner-facing channel (UC-6.11, ADR-0045):

- the owner-facing channel of a tenant: who the owner is, whom they named, where reports go,
  and the phrasebook in the owner's language (`domain/model/channel.py`);
- a report to the owner — a decision request addressed to them, a need, a date or a failure
  Taktus noticed about itself — with what is needed, the steps, what stands still and the date,
  its deliveries and its history (`domain/model/report.py`);
- its three renderings, composed from the report alone: the repository text, the message in
  the owner's channel, and the view (`domain/service/rendering.py`, `application/query`);
- the owner's answer in the channel, read by a rule, reflected back, filed only once the same
  person confirmed it, and only from the owner or someone the owner named
  (`application/service/answer_in_channel.py`).

A broken interface (ADR-0047): an interface Taktus depends on that stopped behaving as its
adapter expects, one per interface and cause, read by a rule from the run's failed calls
(`domain/service/interfaces.py`, through the port `ports/interfaces.py`) and reported to the
owner as a report of kind `failure` (`application/service/broken_interfaces.py`).

The visual vocabulary (UC-6.10, ADR-0059): how every live representation draws a method kind,
an exactness class and a state, as tokens of form, motion, marks and text, defined once
(`domain/model/vocabulary.py`); the glyph of a step or a run, its text equivalent, and the check
that fails a representation drawing an element another way (`domain/service/drawing.py`).

The stream of changes (UC-6.10 §2 *Live*, ADR-0055): what a reader receives as Taktus works —
a snapshot of the scope, then a change for every ledger entry that records a change of state of a
run, a step or a decision request (`domain/model/live.py`, the contract `contracts/changes/v1`).
Whether a reader may see a run is one predicate (`domain/service/visibility.py`), which every
representation asks; until the views of UC-6.4 exist it holds the tenant boundary. The rules —
the projection, the scope, when a resume is a snapshot — are `domain/service/live.py`; what they
read is the port `ports/live.py`, which the composition root binds to the ledger store and the
run's repository; how the streams are fed is the composition root's (`composition/live.py`).

The levels of the live representation (UC-6.10 §1, ADR-0063): what one representation shows at
one of the four levels, drawn from the facts the component that owns them records. The run level
exists: the run and each of its steps, every fact with its glyph with motion and without and its
text equivalent, the waits named by account, cause and role, the figures the run's own
(`domain/model/levels.py`, `domain/service/levels.py`). It is read through the port
`ports/levels.py`, which the composition root binds to the run's repository, and asked of the
one predicate (`application/query/levels.py`). The process level exists too: the steps of a
process version as a graph, each with how it works and the runs it is running in, at rest
otherwise, with the autonomy statement in words and the runs of the version the reader may see;
the predicate answers for a process as well (ADR-0064). And the overview: the areas a reader may
look into — the tenant until the organisation's structure is recorded — the processes in each,
how many of their runs work and wait by the run component's own definitions, and the steps
running now (ADR-0067).

Which connector carries a message, how a decision answer is kept and which values are secret are
asked through `ports/`, and answered by the composition root, because components never import
each other.
"""
