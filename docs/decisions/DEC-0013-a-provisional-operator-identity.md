# DEC-0013 — A provisional operator identity until the identity component exists

**Category:** NOTE
**Raised in:** [#13](https://github.com/Jersyfi/taktus/pull/13), which adds the action half of the connector and the first end-to-end
**Issue:** none; a note is stated, not asked (ADR-0017 §3)

## 1. What this is about

Nothing in Taktus is executed without knowing on whose behalf it acts. A command carries an
identity; a run carries the command's identity; every call a run makes to an outside system —
reading an issue, opening a pull request — carries it too, and the outside system's permissions
for that identity are what limit the call.

The part of Taktus that would *authenticate* a person and map an account on a channel — a
repository hosting service, a chat — to a Taktus identity is the identity component, and it is
planned for `0.2.0`. This pull request needs a command to carry an identity before that
component exists, because a process that opens a pull request must act as someone.

What was built is the smallest thing that does this and nothing more: **one configured
operator identity per tenant.** The operator writes `TAKTUS_PROVISIONAL_IDENTITY=default=idn_owner`
into the instance's configuration, and every command in the tenant `default` — from the
command line, or completed from a webhook delivery — acts as `idn_owner`.

It is provisional, and it says so wherever it appears: the variable's name, the adapter's name
(`ProvisionalOperatorIdentity`), a `provisional: true` field in every resolution it answers, an
`identity_provisional: true` entry in the context of every command it completes, a line on the
command line ("identity idn_owner (provisional: DEC-0013)"), and this record.

## 2. Why you are being asked

You are not. This record was tested against `anchors.md` and fits no row of §1: the identity
component's existence and version are already stated in the roadmap and the architecture; the
provisional identity is the smallest bridge to it and the owner asked for it in the brief of
this pull request. It fits §2 as row D5, the sequencing of work inside an agreed scope, and is
recorded here rather than in the pull request description alone because the provisional
mechanism outlives the pull request and every later reader must find its replacement stated.

## 3. What you must decide

Nothing. The record states what the provisional identity does, what it deliberately does not
do, and what replaces it.

## 4. What you need to know to decide

- **What it does.** Answers, for a tenant, the identity configured for it. From the command
  line, `taktusctl run` and `taktusctl submit` take that identity when `--identity` is not
  given, and refuse to run when neither is there: nothing executes without an identity. On the
  HTTP surface, a webhook delivery the connector accepted is placed in the one configured
  tenant, and `POST /intake-events/{id}/complete` turns it into a command that acts as the
  operator.
- **What it deliberately does not do.** It does not look at who sent the event. Every sender
  of every channel resolves to the tenant's operator — a comment by a stranger on a public
  issue, once completed, acts with the operator's credentials. That is acceptable only while
  the operator is the one person who both configures the instance and owns the channels it
  listens to, which is the state of this repository today; it would not be acceptable for a
  second tenant, and the second tenant is `0.4.0`. It also does not place an intake when more
  than one tenant is configured: guessing a tenant is what the earlier code did and what this
  replaces, so the intake is answered `unknown_sender` and nothing is kept.
- **What replaces it.** The identity component (`0.2.0`): tenants, accounts, the audited and
  revocable mapping from a channel account to one identity, roles. It implements the same port
  (`src/taktus/ports/identity.py`), answers `provisional: false`, and the composition root
  wires it in place of the adapter. Nothing that reads a resolution changes. The variable
  `TAKTUS_PROVISIONAL_IDENTITY` is then removed, not kept as a fallback: a fallback that acts as
  the operator for unknown senders would be the hole this record describes, left open.
- **Where the mark is.** `src/taktus/adapters/driven/identity/provisional.py`,
  `src/taktus/composition/settings.py` (`load_provisional_identity`), `.env.example`,
  `deploy/docker/compose.yml`, `taktusctl run --help`, and the command context.

## 5. Options

None for the owner. What the session did: added the identity port and the provisional adapter;
made the command line and the HTTP surface take their identity from it; made the intake
placement the resolver's answer instead of the first configured tenant; added the completion
of an intake event into a command; marked the mechanism provisional in every place §4 lists.

## 6. What is blocked

Nothing. What waits on the identity component is stated in the roadmap; this record adds the
obligation that the component removes the provisional variable when it arrives.

## 7. How to answer

Nothing to answer. To object to the mechanism — for example, to require that a webhook sender
be checked against an allow-list even before the identity component exists — "Reopen DEC-0013"
in an issue, with what should hold instead.

## Outcome

**Recorded:** 2026-09-19
**Why this is a note:** it states a provisional mechanism and its replacement and asks for
nothing. The identity component and its version are decided (roadmap `0.2.0`, control-plane.md
§2); how to bridge to it inside the agreed scope is the session's to decide and record
(`anchors.md` §2, row D5). It has a record rather than a line in a description because the
mechanism outlives the pull request and the obligation to remove it must be findable.
**Recorded in:** [#13](https://github.com/Jersyfi/taktus/pull/13)
