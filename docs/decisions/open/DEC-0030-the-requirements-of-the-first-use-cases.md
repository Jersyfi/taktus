# DEC-0030 — The requirements of the first use cases

**Category:** NON-BLOCKING
**Raised in:** [#46](https://github.com/Jersyfi/taktus/pull/46)
**Issue:** [#45](https://github.com/Jersyfi/taktus/issues/45)
**Needed by:** 2026-10-20
**Provisional answer:** Option A. The thirteen use cases are in force with the conditions they add beyond version 2 of the definition, which bind any session that builds one of them before the answer. Marked here and in the status file.
**Narrowed:** 2026-10-01, by the owner's answer to DEC-0041: bringing a use case up to his own definition is mode 2. The four amendments this request carried were made under entry M2.7 and recorded as NTC-0014 to NTC-0017; what remains is the thirteen added conditions.

## 1. What this is about

Taktus now has a layer of requirements: one file per thing it must be able to do, each saying
what must be achieved, how that is checked, and what is explicitly not required. A check fails
when one of the fourteen guiding principles is served by no requirement at all. To make that check
real, this pull request had to write requirements covering all fourteen.

Thirteen were written. Each is taken from the project definition — the German document you wrote
— and from the architecture decisions already accepted. The definition mostly gives a sequence and
acceptance criteria in a few words, and a requirement in the new format needs a condition precise
enough that it cannot be met by interpretation. Writing those conditions meant adding substance.
That substance is new, and what a requirement says is yours to decide.

The thirteen were first written against an older version of the definition, of 2026-09-01. The
current one is version 2. Four of them fell short of it; those four have since been brought up to
version 2 without asking you, because you decided on 2026-10-01 that restoring what your own
definition requires is the session's (DEC-0041, NTC-0014 to NTC-0017). This request is now only
about what the session added beyond the definition.

## 2. Why you are being asked

Entry M3.15 of `docs/decisions/anchors.taktus.md`, added in this pull request from your own
brief: *"What a use case requires: its outcome, its verification condition and its boundary —
adding one, changing one, retiring one."* It is mode 3: the session prepares, you decide. Thirteen
requirements were added at once, so the decision is asked once, with every condition that goes
beyond version 2 named below. Bringing a use case up to version 2 is no longer in this entry: it
is M2.7, since DEC-0041.

## 3. What you must decide

Whether the conditions the thirteen requirements add beyond version 2 of the definition stand.

## 4. What you need to know to decide

**Where each goes beyond version 2** — substance the session added:

| Use case | Serves | Added beyond version 2 |
|---|---|---|
| UC-1.1 commands from any channel | P1, P4 | two commands from two channels must be equal except for channel and message; adding a channel changes nothing in the core |
| UC-4.1 a process from a description | P2, P8 | a step no admissible method fits becomes a person's step, never a guess; a rehearsal in which nothing leaves runs before you commission |
| UC-4.5 a step fails: halt or escalate | P10, P12 | a situation package that lacks one of its five parts says which; an escalation past its reaction target is recorded |
| UC-4.10 deviation detection | P8, P10, P12 | the four families of check, from the repository's own text; a step without a check is recorded as *unchecked*, never as passed |
| UC-5.2 control inside or outside, per process | P1, P5 | definition UC-5.1 and UC-5.2 filed as one; the same steps give the same ledger in both modes; switching mode is a new version |
| UC-5.7 no binding to the own dashboard | P1, P7, P13 | every dashboard action exists elsewhere too; a business-intelligence source is read-only unless writing is granted |
| UC-6.1 the complete activity log | P6, P11, P12 | the chain can be exported and verified without Taktus running |
| UC-6.2 reports | P7, P9 | a report without a reader is refused; a quiet period is one sentence |
| UC-6.3 the takeover test | P6, P12, P13 | a person actually carries it out once per process version, and a level-3 or level-4 process without a passed trial is shown as such |
| UC-6.4 role-based views | P7, P14 | a view that groups a figure by person is refused |
| UC-8.9 changing a vendor breaks nothing | P3, P4, P13 | a verdict of *broke* is raised to the owner of every process it names |
| UC-11.1 data residency | P3, P11 | a rule can be narrowed per process and data class, never widened; a binding that breaks it does not register |
| UC-13.5 a person's contribution made visible | P14 | a group so small that it identifies one person is not shown |

**The four amendments are made.** UC-1.1, UC-6.1, UC-6.3 and UC-8.9 asked less than version 2;
each now asks what version 2 asks, recorded as NTC-0014 to NTC-0017. If you disagree with one,
you overrule that notice with a decision; it is not part of this question.

Four of the thirteen are partly built — UC-1.1, UC-4.5, UC-6.1, UC-8.9 — and name the tests that
prove the built part; nine are specified only. None is verified yet. Changing a requirement later is possible, but never in the pull request that
implements it.

## 5. Options

### Option A — the thirteen added conditions stand (recommended)

- **Meaning:** the requirements, with what they add beyond version 2, are the standard the next
  pull requests are held to.
- **Consequence:** the second step of the migration builds on them.
- **Effort:** none now.
- **Reversibility:** cheap until a use case is built; after that, a change is a request per use
  case, which is the intended cost.
- **Why recommended:** each added condition either comes from an accepted architecture decision
  or makes a principle checkable that was only asserted before; none moves a limit or an autonomy
  level.

### Option B — they stand, except the ones you name

- **Meaning:** you name use cases and the added condition you want changed or removed in each; a
  session changes them in a pull request of their own.
- **Consequence:** those use cases wait until the change is merged; the others are in force.
- **Effort:** an hour of your reading, a session's afternoon.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing: the provisional answer is in force. If no answer arrives by 2026-10-20, the second step
of the migration starts on Option A, and changing an added condition afterwards costs a request
per use case instead of one edit now.

## 7. How to answer

"DEC-0030: Option A." — or "DEC-0030: Option B" followed by each use case and the change you
want in it — in issue [#45](https://github.com/Jersyfi/taktus/issues/45).
A free-text answer is read back as an interpretation and confirmed before it is acted on.
