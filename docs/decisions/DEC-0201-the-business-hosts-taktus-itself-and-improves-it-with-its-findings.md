# DEC-0201 — The business hosts Taktus itself, and improves it with its findings

**Category:** NON-BLOCKING
**Mode entry:** M3.2 (what the second tenant's case requires of the product)
**Raised in:** DEC-0199 and NEED-0028, whose fourth question asked where the business's data may go; recorded in the pull request of its own that records the answer
**Issue:** none; the owner answered in conversation, and this record is the question with the answer
**Needed by:** 2026-10-31
**Written after the answer:** the owner answered in conversation on 2026-10-14; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

DEC-0199 made a software business Taktus's second tenant. It left open where the tenant runs:
on the project's instance beside the project's tenant, or on an instance of the business's own
(NEED-0028, question 4). The session had assumed the first.

## 2. Why you are being asked

What the second tenant's case requires of the product is the owner's (M3.2, DEC-0199).

**Sources checked:** DEC-0199, NEED-0027, NEED-0028, UC-03, UC-6.12, ADR-0009, ADR-0012,
ADR-0092, DEC-0044. None says where the business runs Taktus.

## 3. What you must decide

Where the business runs Taktus, who switches its stages, and how its experience reaches the
product.

## 4. What you need to know to decide

As §1.

## 5. Options

### Option A — the business hosts and operates its own instance (recommended)

- **Meaning:** the business installs Taktus, switches its processes over stage by stage itself,
  and the project learns from its findings.

### Option B — the project hosts the business as a tenant

- **Meaning:** as the session first assumed.

## 6. What is blocked

Nothing. #400 waits for the install, the systems and a right to use Taktus (NEED-0028,
NEED-0029).

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-10-14
**Answer:** Option A. "Taktus wird er selbst hosten und dann soll er auch die möglichkeit haben
die Schritte stück für Stück umzustellen wie er aufgezählt hat. Das ist der erste echte Kunde für
Taktus der es selbst einsetzen wird. Für mich wäre es natürlich wünschenswert, wenn so viele
Konnektoren wie möglich in das Taktus Projekt dann mit einfließen und wir so viel wie möglich
bereits vorarbeiten können und am Ende soll mit seinem Feedback, Findings, Bugs Taktus noch
besser gemacht werden." (the owner's words: he hosts Taktus himself and switches the steps over
one by one as he listed them; it is Taktus's first real customer using it itself; as many
connectors as possible should become part of the Taktus project, prepared as far ahead as
possible; his feedback, findings and bugs should make Taktus better.)
**Reasoning given:** the first real customer runs Taktus himself.

**How the session reads the answer.**

1. **The business is its own operator.** It installs, upgrades and runs its instance. The
   project never acts on it. Its data never reaches the project.
2. **It switches the stages itself.** UC-9.6 already gives the stages to the tenant: a person of
   the business opens each stage on Taktus's evidence. The project supplies the blueprint and the
   product.
3. **Every release from `0.4.0` must be installable and upgradable by a stranger.** The road to
   `1.0.0` asked this only at the end ("documentation a stranger can follow", "an upgrade path
   that loses no runs"). For this customer it holds from the first release he installs (#445).
4. **Connectors are product.** Every connector the business needs is built in this repository
   (ADR-0009), named by capability in the core, conformance-tested, and usable by any tenant. What
   can be built before the business names its systems is built first: connectors over open
   standards (#441), and vendors' own servers on the connector protocol (#410, moved to `0.4.0`).
   A connector for each system the business names follows (#447).
5. **Its experience reaches the product as findings.** UC-6.12 already lets an instance outside
   the project raise product findings here once its operator enables it, carrying identifiers,
   causes and durations only. That path is built and switched on for this business (#446). A bug
   it reports by hand is an issue here like any other; its content is checked for the business's
   data before it is posted.
6. **A right to use Taktus.** The repository is public with all rights reserved until the licence
   is decided (ADR-0012, DEC-0044). Running Taktus at the business needs the owner's written
   permission first. That is the owner's act (NEED-0029, #444). The licence itself keeps its timing.

**What it changes:**
- UC-03 §2, §8 and §9;
- NEED-0028's fourth question narrowed to how the business hosts;
- #400 runs on the business's instance; #441 narrowed to connectors over open standards,
  buildable now, and #447 raised for the systems the business names; #410 moved to `0.4.0`;
  #445 and #446 raised;
- NEED-0029 raised.

**What it does not change:** DEC-0199's reading; the licence's timing (DEC-0044); ADR-0013 D —
a version Taktus built is deployed by a person, here the business.

**Recorded in:** [#450](https://github.com/Jersyfi/taktus/pull/450)
