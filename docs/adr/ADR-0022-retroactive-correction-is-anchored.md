# ADR-0022 — Retroactive correction is anchored by default

**Status:** accepted · extends ADR-0008 with a third anchor class

## Context
ADR-0021 introduces the result defect: a run completed, reported success, and its result is
wrong. Once Taktus can detect one (`0.5.0`), the obvious next step is to let it repair one. That
is the dangerous half of the idea, and the reason it needs a decision before an implementation.

A *retry* re-executes a step whose result never counted. A *correction after the fact* changes
a result that has already counted. The two are not the same risk class. Once a wrong value has
reached a tax authority, a partner's system or a customer's invoice, an automatic correction
does not restore one truth. It creates a second one. The partner now holds the old value, Taktus
the new one, and every system between them a mixture. Two truths instead of one wrong one is
more damage, not less.

A retry is safe because its effect has not left Taktus. A correction is safe for exactly the
same reason and for as long as that reason holds. The line is therefore not "retry versus
correction" but "inside versus outside".

## Decision

### 1. Analysis is never anchored
Taktus detects a result defect, bounds its window, analyses its impact and produces a
remediation plan on its own, at any autonomy level. None of that is anchored. An analysis
changes nothing; a plan that is not executed changes nothing. Withholding the analysis until a
person asks for it would only make the person slower.

### 2. Correction inside the system is not anchored
Taktus executes a correction without approval while the effect of the wrong result has not left
the system. Re-running steps, replacing artifacts, recomputing values that nothing outside has
seen: that is a retry with a longer memory, and it stays at the autonomy level of the process.

### 3. Correction after anything has left the system is an anchor
Once anything has left the system, correcting it is an anchor. It stays with a person
regardless of the autonomy level, exactly as legal anchors do. It is a third anchor class,
**correction**, beside the legal and the strategic class of ADR-0008. Every organisation defines
its own anchor set (governance.md §2); this class, like the legal one, can be narrowed but not
removed, because a correction outside the system is an act with effect on third parties.

The anchor halts the remediation at a step boundary and raises a decision request of class
`correction`. Its options are the plan Taktus produced and the alternatives it rejected; the
recommendation is Taktus's. The person decides; the confirmation loop of ADR-0008 applies.

### 4. "Has left the system", defined so that code can check it
A result has left the system when the ledger holds an **egress entry** for it or for anything
derived from it. Three kinds of ledger entry are egress entries:

| Kind | Written when | By |
|---|---|---|
| `egress.write` | a connector wrote outward: an external record created, updated or deleted; a payment released; a file put where another system reads it | the connector adapter, through the run |
| `egress.delivery` | a message, a file or a report was delivered through a channel: chat, mail, a ticket, a shared folder | the channel adapter, through the run or a report |
| `egress.read` | an external system read the result through Taktus: an API response, an export, a feed | the driving adapter that served it |

An egress entry references, in `refs.artifact_ids` together with `refs.run_id` and
`refs.step_id`, the artifacts that went out; a value that went out is referenced by
`content_digest`. It carries nothing else, as every ledger entry does (ADR-0006).

**Derived from** is the provenance chain read forward: the artifacts and results of every step
run whose inputs name the result, transitively, across runs. The predicate is then:

```
left_the_system(tenant, run, step, artifact | value)
  = exists egress entry e in ledger(tenant)
      with (e.refs.run_id, e.refs.step_id, x) ∈ closure
    where closure = {(run, step, artifact | value)}
                  ∪ {outputs of every provenance record whose inputs name a member of closure}
```

`src/taktus/components/governance/domain/service/egress.py` implements it over provenance
records and ledger entries, and `tests/governance` holds it to this table. What is *not* egress:
a worker's own workspace, an artifact in the object store, a value in a checkpoint, a message
to the person who owns the process. Those stay inside Taktus. A worker's tool call is egress
when its capability is one the tenant configured as outward (`0.2.0`); until then a worker that
writes outward is recorded by the connector it writes through, and a worker that has no
connector cannot write outward.

## Alternatives
- **Anchor every correction.** Safe and useless: a correction of a value nothing has seen is a
  retry, and anchoring retries makes level 4 unreachable for exactly the processes that need
  it most.
- **Anchor no correction at level 4.** "Level 4 means unattended" read as "unowned". The
  damage case — two truths at a partner — is the one an unattended system produces fastest.
- **A judgement call per case.** "Has this left the system?" answered by a language model or by
  the person on call is answered differently every time. A predicate over the ledger is
  answered the same way every time, and a person can check the answer.
- **Egress as a flag on the artifact.** A mutable flag on a mutable row; the ledger entry is
  written once and hash-chained, and the impact analysis reads the same source as every other
  metric.

## Consequences
- `contracts/shared/v1/Anchor.json` and `DecisionRequest.json` gain the class `correction`;
  governance.md §2 and `docs/decisions/anchors.md` (M3.11) list it; the ledger's kind vocabulary gains
  `egress.write`, `egress.delivery` and `egress.read` (`LedgerEntry.json`).
- Every connector and channel adapter, when it exists, records an egress entry for what it
  wrote or delivered; every driving adapter that serves a result to an external system records
  `egress.read`. That obligation is part of the connector contract (`contracts/connector/v1`)
  from its first version.
- The remediation plan of UC-4.12 is executed by the run engine like any process, and the
  anchor halts it where the predicate is true. The impact analysis of UC-4.11 reports, per
  affected result, whether it has left the system and through which entry.
- For the Taktus project itself the class applies as well: a correction to something already
  published under the project's name is the owner's (anchors.taktus.md M3.11); a correction to an
  unmerged branch is not.
