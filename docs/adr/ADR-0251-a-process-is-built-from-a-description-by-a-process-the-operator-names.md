# ADR-0251 — A process is built from a description by a process the operator names

**Status:** accepted · extends ADR-0091, ADR-0136 §4, ADR-0030 · UC-4.1 · DEC-0209, DEC-0228

## Context

UC-4.1 requires that a person describes in their own words what should happen, and that Taktus
builds the process from that description, tries it out, and puts it into operation once the
person has commissioned it. A person can change a process in words since ADR-0091: the
configured change process (S-07) turns the words into a proposal, which is rehearsed and
commissioned. A proposal made against no version is a process's first version since
ADR-0136 §4. What was missing is the step from nothing: S-07 reads the active version first, and
`ProposalActs.ask` answered a process the tenant does not have as unknown.

UC-4.1 §2 also requires that the person sees what the rehearsal did, step by step, and what it
would have sent out. A rehearsal's outward step answered from a recording and said nothing of
what it would have sent (ADR-0030).

## Decision

### 1. A description is a request in words for a process the tenant does not have

`ProposalActs.ask` takes the person's words for a process. Where the tenant has the process, the
words are a change, as before (ADR-0091 §2). Where it has none, the words are the process's
description. A run of the process the operator names in `TAKTUS_DESCRIBE_PROCESS` is submitted,
acting for the person, with the inputs `process` — the identifier the new process is to have —
and `description`. The command is recognised as `process.describe`. Without the setting, a
process the tenant does not have is answered as unknown, as before. Which process builds is a
tenant's bundle, never the product's default (ADR-0092).

Every surface that asks in words reaches it unchanged: `POST /processes/{id}/proposals` with
`request`, and `change process <id>: <words>` in the owner's conversation.

### 2. S-08 builds the bundle; registration's validation judges it

The repository's process is S-08 of the self-operation blueprint. A language model writes the
complete bundle, and the loopback connector's `orchestrator.changes.propose` keeps it as a
proposal only if it passes the validation registration applies: every step's method, reason,
methods rejected, fallback and exactness class; an `exact` step from a rule or a statistic with
its check, a `sourced` step with its check (ADR-0233); the autonomy statement with its reason and
what is missing to go higher (ADR-0026); the takeover instructions (ADR-0180). The model is told
to make a step no admissible method fits a `human` step. A bundle that guesses a method against
its class does not register, so no proposal is kept, the step fails with the findings, and the
run goes to a person.

### 3. A rehearsal's outward step says what it would have sent

In a rehearsal, an outward connector operation answered from a recording carries under
`would_send` the operation and its input as resolved. Nothing is sent and no egress is written,
as before. The person reads each step's result of the rehearsal run, in the order the run took
them.

### 4. What stays as it was

Commissioning is the person's act, recorded as `process.commissioned` (ADR-0091 §4). Only a
proposal whose rehearsal finished is commissioned. The proposal is the bundle in the open format
(ADR-0011); a person can read it, change it and register it by hand.

## Alternatives

- **One process for both, S-07 reading an empty version.** S-07's first step would answer a
  bundle that is not there, and its model would be told two jobs in one prompt. Rejected: two
  short processes are each easier to take over by hand.
- **A builder in product code that assembles steps by rule.** No rule set turns words into
  steps; the variable part belongs in a step whose method says so (ADR-0004).
- **Rehearse an outward step without a recording as passed.** A later step that reads its answer
  would then read nothing. Rejected: the rehearsal stays evidence of real answers (ADR-0030).

## Consequences

- An operator who registers S-08 and sets `TAKTUS_DESCRIBE_PROCESS` has processes created from
  words, from the web app's surface and the chat.
- Every rehearsal's outward step result carries `would_send`.

## Where this promise ends

- **Not a right first proposal.** The rehearsal and the person's commissioning are the check.
- **Not an operation never called.** An outward operation the instance has never called for real
  has no recording; its rehearsal fails at that step, and the proposal is not commissioned
  through this path. A person registers such a bundle by hand.
- **Not a page of its own in the web app.** The surface is the proposal's; a form for a new
  process is not built here.
- **Not process discovery** (UC-9.4) and not a method's maturation (ADR-0004).
