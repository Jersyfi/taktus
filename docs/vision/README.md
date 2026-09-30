# The vision layer

Why Taktus exists, what it is for, and what it refuses to be. This layer answers **why**;
`docs/usecases/` answers **what**; `docs/adr/` answers **how it was decided**;
`docs/architecture/` answers **how it is built**.

It is the standard against which point 1 of the definition of done — *violates no guiding
principle* — is checked. Without it that check has nothing to check against.

| File | Contents |
|---|---|
| [vision.md](vision.md) | What Taktus is, its positioning, who it is for |
| [principles.md](principles.md) | The fourteen guiding principles, each with its reasoning and what it forbids |
| [personas.md](personas.md) | The actors and what each one sees |
| [non-goals.md](non-goals.md) | What Taktus deliberately is not |
| [market.md](market.md) | The market picture — **dated, and stale by design** |
| [beyond-1.0.md](beyond-1.0.md) | Ideas that follow from the vision and need a decision after 1.0.0 |
| [history.md](history.md) | Superseded material, kept so that nothing is lost |

---

## How this layer changes

**Mode 4 — the owner decides, a session supplies what the owner needs to decide**
(entry M4.5 of `docs/decisions/anchors.taktus.md`).

This is deliberately unlike ADRs, which for the Taktus tenant are mode 1. The difference is
between the goal and the route to it: a session may choose the route freely as long as the goal
holds, and may not move the goal.

A session that believes a principle is wrong writes a decision request in the seven-section
shape of ADR-0017. It does not edit this layer and then report it.

---

## The relationship to the use cases

Every principle here is served by at least one use case. Every use case points at at least one
principle. Both halves are checked:

- a principle no use case serves is a finding — either an unwritten requirement or an empty
  principle. `make gate-vision` fails on it, and prints which use cases serve which principle
- a use case pointing at no principle is a finding — a requirement with no reason to exist.
  `make gate-usecases` fails on it

`make gate-vision` also holds this layer to itself: the fourteen principles here carry the same
titles as the list in `CLAUDE.md` §5, each states why it exists and what it forbids, every file
of the layer is listed in the table above, and the market picture carries its staleness warning
(`tools/check_vision.py`).

This is what keeps the vision from drifting apart from the product without anyone noticing.

---

## What this layer is not

It is not a specification. It states what must be true, never how. The moment a file here
describes a mechanism, it has crossed into `docs/architecture/` and should move.

It is not a marketing document. A claim here is one the product is held to.
