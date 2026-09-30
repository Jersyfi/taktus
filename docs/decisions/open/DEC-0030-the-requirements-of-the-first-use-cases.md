# DEC-0030 — The requirements of the first use cases

**Category:** NON-BLOCKING
**Raised in:** [#46](https://github.com/Jersyfi/taktus/pull/46)
**Issue:** [#45](https://github.com/Jersyfi/taktus/issues/45)
**Needed by:** 2026-10-20
**Provisional answer:** Option A. The thirteen use cases are in force as written together with the four amendments of section 4, which bind any session that builds one of them before the answer; the files are amended once the answer is recorded. Marked here and in the status file.

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
current one is version 2. Compared with version 2, four of them fall short: version 2 asks
something they do not. Section 4 names each gap and the amendment that closes it.

## 2. Why you are being asked

Entry M3.15 of `docs/decisions/anchors.taktus.md`, added in this pull request from your own
brief: *"What a use case requires: its outcome, its verification condition and its boundary —
adding one, changing one, retiring one."* It is mode 3: the session prepares, you decide. Thirteen
requirements were added at once, so the decision is asked once, with every point where they differ
from version 2 named below.

## 3. What you must decide

Whether the thirteen requirements stand, with or without the four amendments that bring them level
with version 2.

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

**Where four fall short of version 2** — version 2 asks it, the file does not:

| Use case | What version 2 asks | The amendment |
|---|---|---|
| UC-1.1 | every normalised command carries the sender's identity, its context and its reply address (definition UC-1.1, UC-1.7) | section 2 gains: *every command carries the identity of its sender, its context and the address a reply goes to*; section 3's "not identity" is narrowed to *whether the sender may give the command*. The order in which channels are connected — ticket system, repository, team chat, command line, web — is the roadmap's (M1.7), not the use case's |
| UC-6.1 | the log records which worker acted, is fed from the workers' event stream, and is exportable as a telemetry signal (definition UC-6.1) | section 2 gains: *the log can be exported as a telemetry signal, entry by entry, with nothing the ledger itself would not carry*; section 3's "not an operational log" keeps the distinction but no longer excludes the export |
| UC-6.3 | the takeover documentation names the skills a process uses (definition UC-6.3, UC-14.2) | the list of what the instructions name per step gains *the skills the step uses, by version* |
| UC-8.9 | every process can be exported as one coherent package, skills included (definition UC-8.9) | section 2's export condition becomes: *everything that defines a process — definition, prompts, skills, configuration, instructions — can be exported as one package per process, in an open format, and read without Taktus* |

Four of the thirteen are partly built — UC-1.1, UC-4.5, UC-6.1, UC-8.9 — and name the tests that
prove the built part; nine are specified only. None is verified yet. None of the four amendments
touches a built part. Changing a requirement later is possible, but never in the pull request that
implements it.

## 5. Options

### Option A — the thirteen stand, with the four amendments (recommended)

- **Meaning:** the requirements are the standard the next pull requests are held to, amended in
  four places to what version 2 asks. A session applies the amendments in a pull request with
  nothing else in it.
- **Consequence:** the seeds and the definition agree; the second step of the migration builds on
  them.
- **Effort:** an hour of a session's time.
- **Reversibility:** cheap until a use case is built; after that, a change is a request per use
  case, which is the intended cost.
- **Why recommended:** each amendment only restores what the definition already required, and
  each added condition in the first table either comes from an accepted architecture decision or
  makes a principle checkable that was only asserted before; none moves a limit or an autonomy
  level.

### Option B — the thirteen stand as written

- **Meaning:** no amendment; the four gaps stay.
- **Consequence:** four requirements ask less than the definition; each gap comes back as its own
  request when someone builds against the definition.
- **Effort:** none now.
- **Reversibility:** cheap until built.

### Option C — they stand, except the ones you name

- **Meaning:** you name use cases and what should change in each, beyond or instead of the four
  amendments; a session changes them in a pull request of their own.
- **Consequence:** those use cases wait until the change is merged; the others are in force.
- **Effort:** an hour of your reading, a session's afternoon.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing: the provisional answer is in force. If no answer arrives by 2026-10-20, the second step
of the migration starts on Option A, and changing a requirement afterwards costs a request per use
case instead of one edit now.

## 7. How to answer

"DEC-0030: Option A." — or "DEC-0030: Option B." — or "DEC-0030: Option C" followed by each use
case and the change you want in it — in issue [#45](https://github.com/Jersyfi/taktus/issues/45).
A free-text answer is read back as an interpretation and confirmed before it is acted on.
