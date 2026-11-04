# ADR-0200 — Model routing proposes a trial of a member it switched to

**Status:** accepted · builds on ADR-0149 §3 and the routing of #328 (ADR-0116 §4) · issue #448

## Context

ADR-0149 offers a trial when Taktus proposes another model for a purpose. Its hook,
`Trials.propose`, had no caller: nothing in the instance proposed a model. Two candidates were
named for it, model routing and method maturation.

Routing serves each purpose by an ordered chain of members and switches at the step boundary
when a member cannot answer — at its rate limit, cooling down, or not allowed where the step's
data may go. The member behind the first then answers the purpose's steps. No person chose it
for that purpose, and no trial may have included it. That is exactly the case ADR-0149 §3 means:
another model now serves the purpose.

Method maturation proposes moving a step from a language model to a trained model (ADR-0084).
A trained model is not a member of a purpose's chain, and a trial compares members. Maturation
has its own trial run on held-out cases, so it is not a caller here.

## Decision

Once an hour the scheduler reads every tenant's `step.finished` entries that name a model
member and a step of a process version (`Trials.routed`, `trials_tick`). For each it reads the
purpose the version's step asks for. A member that answered a step of a purpose while it stands
behind the first member of that purpose's chain is a member routing switched to. Where no trial
of the purpose included it and Taktus has not proposed it for the purpose before, Taktus calls
`Trials.propose` with the reason: the chain's first member, the member, and how many steps it
answered. The offer then stands as ADR-0149 says, until a trial includes the member or a person
declines it.

The proposal binds nothing and starts nothing. A rehearsal's entries are not read.

## Alternatives

- **Propose on every switch.** A member that answers often would be proposed again and again,
  and a decline would never hold. One proposal per purpose and member is enough to bring the
  question to a person.
- **Start the trial on the switch.** ADR-0149 §3: a trial is offered, never started on its own.
- **Maturation as the caller.** A trained model is no chain member; see Context.

## Consequences

- `Trials.routed` and `trials_tick` in `composition/trials.py`; the scheduler calls the tick.
- `proposed` offers appear on the *Trials* page and on `GET /trials/offers` without anyone
  calling `propose` by hand.

## Where this promise ends

- A member is seen only once it answered a step. A switch that failed over to a member that also
  could not answer leaves no trace here.
- The purpose is read from the step's current process version. A step whose version is gone
  proposes nothing.
- A member proposed once is not proposed again for the same purpose, even if a person declined it
  and routing keeps switching to it.
- Maturation proposes no model for a trial.
