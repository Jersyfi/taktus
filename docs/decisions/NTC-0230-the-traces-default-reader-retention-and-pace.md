# NTC-0230 — The trace's default reader, retention and pace

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-23
**Raised in:** [#614](https://github.com/Jersyfi/taktus/pull/614), which builds #409
**How it follows:** UC-6.14 requires a retention set per tenant with a default "the architecture names", and a trace shown only to whom it is entitled and shared by role; it names neither the default nor the first reader. The decisions follow the existing defaults of the same kind: the owner's role as the decider an anchor names when it names none (`components/governance/domain/model/anchors.py`, `OWNER`), and a short retention for content that is not a record (strict in substance, sparing in ceremony).

## 1. What was decided

- **The default reader of a trace is the role `owner`.** A trace is shown to the readers of its
  run who hold that role, or a role it is shared with. A tenant cannot name another default yet.
- **The default retention is 30 days**, settable per tenant from 1 to 3650 days.
- **The web app asks for new lines every two seconds** while a step is in flight, and the
  scheduler erases expired lines once an hour.

## 2. The evidence

- UC-6.14 §2: "a tenant that set nothing holds a default the architecture names"; "A person who
  may see a trace shares it with a role."
- The anchors' default decider is the role `owner` (ADR-0042); the owner-facing channel serves
  `owner` by default (`reporting/domain/model/channel.py`).
- UC-6.10 and UC-6.14 bound liveness at 5 seconds; two seconds of waiting leaves three for the
  read.

## 3. What was considered

- **Every reader of the run sees the trace.** Rejected: a share would then grant nothing.
- **No default reader; only shares.** Rejected: nobody could share the first trace.
- **A retention of 90 days or more.** Rejected: the trace holds a worker's own words and is not
  an archive; a tenant that needs longer sets it.

## 4. Which entry permits it

No entry of modes 3 or 4 names who reads a step's trace by default, how long a tenant keeps it
before it sets a retention, or how often the web app asks again. None of them spends, and none
widens what a role may see of runs: the run's predicate is asked first. No entry of mode 2 names
them either, so M2.6 applies.

## 5. The entry it proposes

**M1.25** — *The shipped default of a tenant setting that keeps content for a time: the shortest
period that serves its use case, settable by the tenant.* And, for the reader, the precedent of
the anchors applies: the role `owner` where no other is named.
