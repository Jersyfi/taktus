# ADR-0042 — Anchors halt at the step boundary and raise a decision request

**Status:** accepted · builds ADR-0008's anchors and decision requests, and ADR-0022's correction class, into the product

## Context
An **anchor** keeps an act with a person whatever the autonomy level (ADR-0008). Three classes
exist: legal, strategic and correction (ADR-0022). A **decision request** is the planned question
an anchor raises: one fixed shape, a confirmation loop, an entry in the decision register. Until
now both existed only as contracts (`Anchor.json`, `DecisionRequest.json`) and as this
repository's own hand-run register (ADR-0017). The product evaluated no anchor. A run at level 3
would have performed an act a tenant had anchored.

UC-7.4 §2 and the anchor condition of UC-7.1 §2 ask for more (issue #79, provisional under
DEC-0069). A tenant's anchors are configuration that is never emptied. An anchored act halts the
run at the step boundary at every level. The request has one shape, and one missing a part is not
raised. A free-text answer takes effect only once its reading is confirmed. Every answered request
is an entry in the register. Waiting work is visible, and nothing waits silently. A decider's
response times are theirs alone (ADR-0015).

Four questions had to be answered. Where does a tenant's configuration live, and what does it hold
when the tenant configured nothing? How does an anchor select a step? Who may answer, and how is an
answer read? How is a response time kept from becoming a measure of a person?

## Decision

### 1. A tenant's anchors are a configuration governance keeps, never emptied
An **anchor configuration** is one tenant's set of anchors, each in the shape of `Anchor.json`,
and the tenant's **risk classes**. A risk class is a name for a set of tool actions, given as
capability patterns. It lives beside the anchors so that an anchor selecting by risk class can be
checked: the definition of the classes is the tenant's (UC-7.1 §3).

A configuration is refused, and nothing is stored, when it leaves the legal or the correction
class empty, names an anchor twice, scopes an anchor to another tenant, or selects a risk class it
does not define. An anchor that could never apply is a hole, not a choice. The strategic class may
be empty (ADR-0008, *Where this promise ends*).

`taktusctl anchors set FILE` stores a configuration, and `anchors.configured` records its digest
and who configured it. A tenant that configured nothing holds the **shipped default**: one legal
anchor on `legal.*` and `payment.release`, one correction anchor on `correction.*`, both decided
by the role `owner`. The default's legal anchor is the project's own list and is not legally
reviewed (DEC-0029). The catalogue per domain and jurisdiction is UC-15.5.

### 2. An anchor selects a step by its tool actions, its process and its risk classes
A step's tool actions are what ADR-0039 already names: the capabilities it requires, and the
connector operation it calls or waits on with that operation's capability. An anchor applies to a
step when **every selector it gives matches, and within one selector any item does**. The
contract's own examples read that way: `payment.release:*` together with the risk class
`financial.high` anchors a payment release of high risk.

A capability pattern matches segment by segment. `*` as a segment matches one segment, and as the
last segment everything below it. A qualifier narrows: a pattern without one, or with `:*`,
matches every qualifier. An anchor's `domain` and `jurisdiction` are not evaluated until domains
exist (UC-15.5); such an anchor holds everywhere in the tenant meanwhile, never less than
configured.

### 3. The anchor is asked first at the boundary, before the level and before the estimate
Before anything of a step starts, the run engine asks which anchors name the step's act
(`run/ports/anchors.py`, answered from governance by the composition root). This comes before the
level of ADR-0039 is applied and before the step is estimated, at every level. For each anchor
that applies, the engine raises one decision request in the decision component and the step waits
in `waiting_human` (`step.anchored`). Steps that do not depend on it run on, as for a
confirmation. A rehearsal acts on nothing outside and is asked no anchor (NTC-0079).

The request has two options. **A** performs the act as the process proposes it; it is
recommended, and its reason says that the registered process proposes the act here and the anchor
keeps the decision with the person. **B** does not perform it. The request is due
`decision_days` after it is raised, three by default. Its identifier is derived from the run, the
step, the anchor and the round, so a request raised again after a crash is the same request.

A request that cannot be raised — a part missing, or no decision port wired — fails the step
without its act, and the run escalates. Neither an anchored act nor a silent wait is left.

`taktusctl run --approve` cannot confirm an anchored step. An anchored act is decided through its
request, by the person the anchor names.

### 4. One shape, a reading confirmed, an entry in the register
The decision component builds the request in the shape of `DecisionRequest.json` and refuses it
with `NotRaised` when a part does not hold. The recommended option now carries its **reason**: the
contract gains `options[].reason`, required on the recommended option. The request's channel is
the control plane's own surface (`controlplane.decisions`, addressed to `role:<role>`); the chat
rendering is the owner-facing channel's (#85).

**Who answers.** An identity holding the role the anchor names. Identities gain **roles**,
which the identity component keeps (`taktusctl identity add --role`, `identity roles`). Only the
identity whose answer was read confirms its reading.

**How an answer is read.** By a rule, never by guessing: the answer names exactly one option,
as a letter standing alone or as "option B". Words around it are kept with the decision, and Taktus
does not act on them. An answer from which no single option can be read changes nothing, and the
message asks for one. Every answer, a chosen option as well as free text, is reflected back in
one message, and only a confirmed reading takes effect. ADR-0008 has every decision cost one
confirmation message.

**What takes effect.** On confirmation the request becomes `applied`, and the register gains its
entry, linked to the run, the step and the request (`decision.confirmed`, `decision.applied`).
This happens in the same transaction. The engine's `decide` then reads the verdicts
(`step.decided`). A step whose requests all said A continues from its boundary; at level 2 the
decision is the person's confirmation, and at level 1 the person still performs the act. A step
any request declined is not run, and the run halts with cause `declined`. A resume raises the
request again, in a new round. On the HTTP surface, a confirmed decision hands the run to a
runner through the queue.

### 5. Nothing waits silently
The run's reason and its ledger name the request, the role it is addressed to and its due date
(`step.anchored`, `decision.raised`, each with `refs.decision_request_id`). The decider's list,
`GET /decisions` with the account key of ADR-0040, holds every request not yet applied whose role
the reader holds, the oldest due first. It marks one past its due date as `overdue`.

### 6. A response time is the decider's
`GET /decisions/response-times` returns the reader's own times, each decision with its time.
Everyone else's times are returned only aggregated, by the role that decided and by the
department of the deciders, never by person and never ranked. An aggregate over fewer than two
deciders is withheld, count and all, because it is one person's number under another name. A
request shown to a decider who did not answer it names no answerer and no answer time. The rule
lives in what the read returns (ADR-0015).

## Alternatives
- **Selectors combined as any-of.** More halts, but the contract's examples would mean something
  else: "a payment release of high risk" would anchor every release and everything of high risk.
- **Risk classes declared by each process.** A process would grade its own risk, and an anchor on
  a class no process declares would never apply without anyone noticing.
- **A free-text answer read by a model.** It could read more intent, and it would have to be
  confirmed all the same. A rule is reproducible, and its failure is visible in the reflection
  before anything happens.
- **A chosen option applied without confirmation.** Less ceremony, but ADR-0008 prices one
  confirmation message into every decision, and the reading of a click can be wrong too.
- **Anyone in the tenant may answer**, as anyone may confirm a level-2 step (ADR-0039). The anchor
  names a role, and an act kept with a person is kept with that person.
- **One request per step for all its anchors.** The anchors can name different roles, and one
  request has one addressee.

## Consequences
- `governance`: `AnchorConfiguration`, `AnchorsInForce`, `ConfigureAnchorsHandler`; the
  matching rule in `domain/service/anchors.py`. `decision`: `Request`, `RegisterEntry`, the
  handlers that raise, answer and confirm, the queries, the reading rule and the response-time
  rule; its port `Deciders`. `run`: the ports `Anchors` and `Decisions`, `StepRun.anchoring`,
  cause `declined`, `RunEngine.decide`. Identity: `Identity.roles`, `Resolution.roles`.
- Ledger kinds `anchors.configured`, `step.anchored`, `step.decided`, `decision.raised`,
  `decision.answered`, `decision.reread`, `decision.confirmed`, `decision.applied`,
  `identity.roles_set`.
- `DecisionRequest.json`: `options[].reason`, required on the recommended option; its examples
  carry one, and one without it must fail. The contract is `v1` and no released version uses it
  (ADR-0019).
- Migration 0017: `anchor_configuration`, `decision_request`, `register_entry`,
  `step_run.anchoring`, `identity.roles`.
- HTTP: `GET /decisions`, `GET /decisions/{id}`, `POST /decisions/{id}/answer`,
  `POST /decisions/{id}/confirm`, `GET /decisions/response-times`. Command line:
  `taktusctl anchors set|show`, `taktusctl identity add --role`, `taktusctl identity roles`.

## Where this promise ends
An anchor is asked before a step starts. A step that started before its anchor was configured is
not asked again, as ADR-0039 says of levels. The anchor names what a step uses — its
capabilities, its connector operation — and not what a worker does inside its frame; a worker
that writes outward without a connector is invisible to an anchor until worker egress is recorded
(ADR-0022). The correction class triggers on its selectors; the egress predicate as its trigger
arrives with remediation in `0.5.0`. `domain` and `jurisdiction` are not evaluated before
UC-15.5. The reading rule finds an option letter, not intent: "A" in "A good idea" reads as
option A, and the reflection is what catches it. A person who confirms a wrong reading has
decided wrongly; the loop protects against a misread answer, not a wrong one (ADR-0008). The
ledger is the audit log (UC-6.1) and records who answered and when, so a person allowed to read a
run's ledger can compute a response time by hand. The protective rule governs what Taktus computes
and shows. Requests are reached on the control plane's surface only; a chat message and the web
app's page are #85 and `0.3.0`. Rules from precedent are `0.6.0`.
