# ADR-0338 — A rehearsal's escalation reaches nobody, and a read of Taktus by an input is not rehearsed

**Status:** accepted · amends ADR-0030 §3 and ADR-0316 §1 · UC-4.5, UC-8.9

## Context

A **rehearsal** is a run that acts on nothing outside: an outward connector operation answers
from the recording of its last real call (ADR-0030). The removal test rehearses every process
that uses the integration it tests, twice: once with the integration and once without it.

On 2026-11-15 and again on 2026-11-18, the removal test rehearsed S-09, the conversation turn.
S-09's first step reads the person's conversation from Taktus itself, through the loopback
connector. A loopback step is not outward, so a rehearsal calls it for real. The removal test
gives a rehearsal every input's example, and S-09's example conversation does not exist on the
instance. Both rehearsals failed at that first step and escalated. The escalation watch of
ADR-0252 then delivered each escalation to the owner as a failure, with the options "remove the
cause and resume, do the step by hand, or leave it stopped". Two messages arrived at the same
minute, about runs that acted on nothing, and their options made no sense for a rehearsal.

Two faults met here. The removal test rehearsed a process whose rehearsal could not succeed,
so its verdict for that process measured nothing. And a rehearsal's escalation was told to a
person as if it were a real run's.

## Decision

### 1. A rehearsal's escalation reaches nobody

The escalation watch records the escalation of a rehearsal run as `escalation.not_sent` with
the outcome `rehearsal`, marked as a rehearsal's entry. It raises no report and sends no
message, and the escalation is never overdue. What a rehearsal came to is read where it was
asked for: in the removal verdict, or in the proposal it was run for (ADR-0091). The start
page already leaves a rehearsal's escalation out (`today.py`).

### 2. A process that reads Taktus itself by an input is not rehearsed

ADR-0030 §3 names three conditions under which the removal test rehearses a process. A fourth
is added: no step that Taktus answers through the loopback connector takes a value from a run's
input. Such a step reads what the input's example names, and an example names nothing the
instance holds. When the condition fails, the verdict for the process rests on resolution
alone, as for the other three, and the finding names the steps: `not run: step(s) context read
Taktus itself by an input, and an input's example names nothing it holds`.

## Alternatives

- **Give the rehearsal a real conversation.** The removal test would have to create one, which
  is a write, and choose whose it is. A rehearsal acts on nothing, so it cannot.
- **Answer the loopback from a recording too.** A loopback read is not recorded, and a recorded
  conversation is a person's words kept in a run's record. That is not wanted for a test.
- **Leave delivery as it is and only fix the removal test.** Any other rehearsal that fails,
  for example a proposal's, would still reach a person as a failure of a real run.

## Consequences

- The weekly removal test sends no message about its own rehearsals.
- S-09 is resolved for the integration it uses, not rehearsed. Its verdict says why.
- A rehearsal that escalates is visible in the ledger and in the run's own page, not in the
  owner's channel.

## Where this promise ends

The watch recognises a rehearsal by the mark on its `run.escalated` entry (ADR-0030 §2). An
escalation already delivered before this decision stays delivered. A broken removal verdict
is still raised to its owner (ADR-0300 §3): that is the verdict, not the rehearsal's
escalation. The fourth condition reads the step's work as its bundle wrote it. A loopback read
that names its subject in a fixed value, not by an input, is still rehearsed, and fails if
that subject does not exist. A step that reads Taktus without any input, such as the list of
integrations, is rehearsed as before.
