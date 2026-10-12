# DEC-0185 — The web app is one body that works, and its look is the session's

**Category:** NON-BLOCKING
**Raised in:** the session that takes up the milestones `0.1.0` to `0.3.0`, on 2026-10-12, from the owner's feedback that the web app is neither appealing nor easy to understand; recorded in the pull request of its own that records the answer
**Issue:** none; the owner answered in conversation before a request was written, and this record is the question with the answer
**Needed by:** 2026-10-12
**Written after the answer:** the owner answered in conversation on 2026-10-12; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

The owner found the web app of `0.3.0` neither appealing nor easy to understand, and asked for a
design concept: modern, plain and clear, and alive like an organism. The session showed two
drafts as a local preview. The owner rejected the first one's symbols as too drawn. The second
draft is called *one body that works*:

- every process is an organ, and every step is a cell;
- vessels join each step to the steps that follow it;
- a cell's membrane says how the step works, and its nucleus says which method kind;
- rings on the membrane say the exactness class;
- the cytoplasm and a small badge say the state.

Reproducible cells have a crisp, evenly beaded membrane and contract in one shared beat. Variable
cells have a fluid membrane that changes shape while they work. A person's cell breathes slowly.
A waiting cell is a dormant spore and never moves. Each level of the web app opens with a
sentence that says what is happening, and the picture follows it.

NTC-0127 chose the vocabulary's tokens under *Neither list* (M2.6). It proposed an entry for this
page: the look of a representation is the session's, within the distinctions UC-6.10 requires.
The second draft replaces those tokens.

## 2. Why you are being asked

Accepting an entry that a notice proposes is the owner's (DEC-0039). The design direction of the
web app is not the session's to fix alone while M1.20 is not an entry.

**Sources checked:** UC-6.10 §2 and §3 and DEC-0055 (which distinctions are required, and that no
style is), NTC-0127 (the proposed entry), both anchor pages (no entry names the look) and the
register (DEC-0039, DEC-0049, an entry accepted from a notice's proposal).

## 3. What you must decide

Whether the web app follows *one body that works*. Whether M1.20 becomes an entry of this page.

## 4. What you need to know to decide

- **A distinction** is something UC-6.10 requires the picture to tell apart. For example:
  reproducible steps from variable ones, a person's step and a waiting step from both, `exact`
  from every other class. A distinction is carried by form and motion, never by colour alone.
- **M1.20** leaves the tokens and how they are rendered to the session. Dropping a distinction
  stays a change of what the use case requires (M3.15).

## 5. Options

### Option A — the direction, and M1.20 as proposed (recommended)

- **Meaning:** the web app is built to the second draft, and the look is mode 1 within the
  distinctions UC-6.10 requires.
- **Consequence:** the tokens of NTC-0127 are replaced. A notice records the new tokens.
- **Effort:** the web app's levels and the vocabulary in `reporting`.
- **Reversibility:** cheap. The owner may override a look at any time.
- **Why recommended:** the owner's answer, below.

### Option B — the direction, but each change of the look is asked

- **Meaning:** M1.20 is not an entry. Every further change of the look is a request.

## 6. What is blocked

The web app's new look.

## 7. How to answer

"DEC-0185: Option A.", "DEC-0185: Option B." or the owner's own wording.

## Outcome

**Decided:** 2026-10-12
**Answer:** Option A. "The direction of the design fits and is approved, and I also approve the rule question from before." (the owner's words, translated)
**Reasoning given:** none beyond the answer.
**What it does not change:** what UC-6.10 requires. Dropping a distinction it prescribes stays M3.15.
**Recorded in:** this pull request: `anchors.taktus.md` gains M1.20 and its history line. `anchors.md`, the shipped default, does not: the owner answered for this tenant.
