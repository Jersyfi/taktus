# ADR-0255 — Taktus changes a process within the frame its owner declares

**Status:** accepted · extends ADR-0011, ADR-0091, ADR-0084 · UC-4.3 · DEC-0228

## Context

UC-4.3 requires that Taktus makes a small change to a process itself — an interface it calls
changed its shape, a step became mandatory — as long as the change lies within the frame the
process's owner set. Every such change is a new version that records what changed, why, and the
observation that led to it; rolling back is one act; the version passes the same registration as
one a person writes, or the change becomes a proposal. A change outside the frame is a proposal,
and five changes are outside whatever the frame says: raising autonomy (ADR-0026), changing a
step's method kind (ADR-0004), loosening an exactness class (ADR-0014), removing or narrowing an
anchor (ADR-0008), and widening what a step may reach or which credentials it receives (UC-7.3).

A version could not say what Taktus may change in it. The one built change outside the frame was
a method move (ADR-0084, ADR-0114). A proposal (ADR-0091) carried a person's words, not an
observation.

## Decision

### 1. The frame is a declaration of the version

A bundle's `frame.changes` lists the kinds of change Taktus may make on its own:

- `work` — a step's work, the operation and the capability it calls unchanged: the fields it
  sends, the part it selects, the values it maps;
- `step_added` — a step added that the others do not depend on through any change of theirs;
- `checks_added` — a check added to a step; none removed or changed;
- `takeover` — the takeover instructions' words.

Without `frame`, every change is outside. The frame is the owner's: a change of the frame is
outside it.

### 2. What is always outside

The process component's rule (`domain/service/change.py`) compares the new version with the
active one and names every change of these, whatever the frame says:

- a level the autonomy statement raises (`autonomy.raises`, ADR-0039);
- a step's method kind changed;
- a step's exactness class moved to a looser one, or dropped from a step that produces a result;
- an anchor removed or narrowed: a `human` step removed, an `approval` check removed or its
  threshold raised, a `sampling` check removed or its share lowered;
- a step's reach widened: a capability or operation it uses that no step used before, a
  credential its work names that it did not, a host it may reach that it could not;
- the frame changed.

Every other change is of one of the kinds of §1, or of none — a trigger, an input, a limit —
and a change of no kind the frame lists is outside.

### 3. A change within the frame is a version; one outside is a proposal

`ChangeWithinFrame` (`application/service/change_within_frame.py`) takes the changed bundle and
the observation: what was observed (`failure`, `interface` or `run`), the run or the operation
it was observed on, and what was observed, in words. Within the frame the bundle is registered
through the one registration a person's version goes through, takeover instructions included,
acting for the identity that activated the version it replaces, with `author: taktus`, the
reason given, and `change`: the observation, the predecessor and every change in words. The
ledger records `process.changed`. The replaced version stays registered and unchanged.

Outside the frame, or where registration refuses the version, the bundle becomes a proposal
(ADR-0091 §1) that carries the observation and every reason it is not a version; nothing of it
runs before a person commissions it. The ledger records `process.change_proposed`. A bundle
whose parts registration cannot even read is refused and recorded with its findings.

### 4. Rolling back is the rollback of ADR-0091 §5

A person rolls back to the predecessor in one act, at any time, as a new version. A rollback
carries the frame and not the change record of the version it restores: it is a person's act.

## Alternatives

- **The frame as a tenant setting.** A frame belongs to a process; two processes of a tenant
  admit different changes, and a version must say what it admitted when it was registered.
- **Changes within the frame without registration.** A version not held to registration's rules
  is one a person could not have written, which UC-4.3 forbids.

## Consequences

- `frame` and `change` are new bundle fields; `process.changed` and `process.change_proposed`
  are new ledger kinds. A proposal carries `change` and `findings`.
- The postgres mapper stores them, with the version's `escalation` and `heal_limit`, which it
  did not store (DEC-0233, migration `0104`).

## Where this promise ends

- **What Taktus observes is given.** Which failure or changed interface leads to which bundle is
  the caller's; this decision decides what follows from a changed bundle, not how it is written.
- **The tenant's own anchors are not in a version.** The anchors of `anchors.md` are the
  tenant's configuration, which no version changes; §2 holds the anchors a version carries.
- **Reach is read from the bundle.** A host or a credential named by a reference is known only
  when a run resolves it, as registration's refusal of the platform's credentials is.
