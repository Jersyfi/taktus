# DEC-0030 — The requirements of the first use cases

**Category:** NON-BLOCKING
**Raised in:** [#46](https://github.com/Jersyfi/taktus/pull/46)
**Issue:** [#45](https://github.com/Jersyfi/taktus/issues/45)
**Needed by:** 2026-10-20
**Provisional answer:** Option A. The thirteen use cases are in force as written; the second step of the migration builds on them. Marked here and in the status file.

## 1. What this is about

Taktus now has a layer of requirements: one file per thing it must be able to do, each saying
what must be achieved, how that is checked, and what is explicitly not required. A check fails
when one of the fourteen guiding principles is served by no requirement at all. To make that check
real, this pull request had to write requirements covering all fourteen.

Thirteen were written. Each is taken from the original project definition — the German document
you wrote — and from the architecture decisions already accepted. But the definition mostly gave
a sequence and acceptance criteria in a few words, and a requirement in the new format needs a
condition precise enough that it cannot be met by interpretation. Writing those conditions meant
adding substance: thresholds of what counts, what must be refused, what is proven how. That
substance is new, and what a requirement says is yours to decide.

## 2. Why you are being asked

Entry M3.15 of `docs/decisions/anchors.taktus.md`, added in this pull request from your own
brief: *"What a use case requires: its outcome, its verification condition and its boundary —
adding one, changing one, retiring one."* It is mode 3: the session prepares, you decide. Thirteen
requirements were added at once, so the decision is asked once, with the points where the session
went beyond the definition named below.

## 3. What you must decide

Whether the thirteen requirements stand as written, or which of them change before the next step
of the migration builds on them.

## 4. What you need to know to decide

The thirteen, by the principle each was written to serve first, with the substance the session
added beyond the definition:

| Use case | Serves | Added beyond the definition |
|---|---|---|
| UC-1.1 commands from any channel | P1, P4 | two commands from two channels must be equal except for channel and message; adding a channel changes nothing in the core |
| UC-4.1 a process from a description | P2, P8 | a step no admissible method fits becomes a person's step, never a guess; a rehearsal in which nothing leaves runs before you commission |
| UC-4.5 a step fails: halt or escalate | P10, P12 | the situation package has five named parts and says which one it lacks; an escalation past its reaction target is recorded |
| UC-4.10 deviation detection | P8, P10, P12 | taken from the repository's own text; added from the draft: a step without a check is recorded as *unchecked*, never as passed |
| UC-5.2 control inside or outside, per process | P1, P5 | definition UC-5.1 and UC-5.2 filed as one; the same steps give the same ledger in both modes; switching mode is a new version |
| UC-5.7 no binding to the own dashboard | P1, P7, P13 | an automated test finds every shown figure in the export; every dashboard action exists elsewhere |
| UC-6.1 the complete activity log | P6, P11, P12 | the chain can be exported and verified without Taktus running |
| UC-6.2 reports | P7, P9 | a report without a reader is refused; a quiet period is one sentence |
| UC-6.3 the takeover test | P6, P12, P13 | a person actually carries it out once per process version, and a level-3 or level-4 process without a passed trial is shown as such |
| UC-6.4 role-based views | P7, P14 | a view that groups a figure by person is refused |
| UC-8.9 changing a vendor breaks nothing | P3, P4, P13 | a replacement reaches real runs only after a validation run has reported per process |
| UC-11.1 data residency | P3, P11 | a rule can be narrowed per process and data class, never widened; a binding that breaks it does not register |
| UC-13.5 a person's contribution made visible | P14 | a group so small that it identifies one person is not shown |

Four of the thirteen are partly built — UC-1.1, UC-4.5, UC-6.1, UC-8.9 — and name the tests that
prove the built part; nine are specified only. None is verified yet. Changing a requirement later
is possible, but never in the pull request that implements it: whoever builds one and finds it does
not hold raises a request with the point where it fails.

## 5. Options

### Option A — the thirteen stand as written (recommended)

- **Meaning:** nothing changes; the requirements are the standard the next pull requests are held
  to.
- **Consequence:** the second step of the migration builds on them; a requirement found wrong while
  building comes back as its own request.
- **Effort:** none now.
- **Reversibility:** cheap until a use case is built; after that, a change is a request per use
  case, which is the intended cost.
- **Why recommended:** every added condition is either taken from an accepted architecture decision
  or makes a principle checkable that was only asserted before; none moves a limit or an autonomy
  level.

### Option B — they stand, except the ones you name

- **Meaning:** you name use cases and what should change in each; a session changes them in a pull
  request of their own, with nothing else in it.
- **Consequence:** those use cases wait until the change is merged; the others are in force.
- **Effort:** an hour of your reading, a session's afternoon.
- **Reversibility:** cheap.

### Option C — withdraw them and write only what the definition says

- **Meaning:** the thirteen files are cut back to the definition's words.
- **Consequence:** most would no longer have a condition a check can hold them to, and the rule
  that a requirement is verifiable would fail on them; the principle coverage would hold on paper
  only.
- **Effort:** a session's afternoon.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing: the provisional answer is in force. If no answer arrives by 2026-10-20, the second step
of the migration starts on Option A, and changing a requirement afterwards costs a request per use
case instead of one edit now.

## 7. How to answer

"DEC-0030: Option A." — or "DEC-0030: Option B" followed by each use case and the change you want in it —
or "DEC-0030: Option C." in issue [#45](https://github.com/Jersyfi/taktus/issues/45). A
free-text answer is read back as an interpretation and confirmed before it is acted on.
