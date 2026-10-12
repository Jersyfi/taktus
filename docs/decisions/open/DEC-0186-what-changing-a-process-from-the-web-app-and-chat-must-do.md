# DEC-0186 — What changing a process from the web app and chat must do

**Category:** NON-BLOCKING
**Mode entry:** M3.15
**Raised in:** the pull request that records it, while making the `0.3.0` track *create, change and roll back a process from the web app and chat* ready: no use case says what changing a process by a person must achieve
**Issue:** [#293](https://github.com/Jersyfi/taktus/issues/293)
**Needed by:** 2026-10-26
**Provisional answer:** Option A. UC-4.15 is in force as written, and its tasks are built against it. Marked in the use case's section 4 and in the status file.

## 1. What this is about

Version `0.3.0` is complete when *a process can be created, viewed, changed and rolled back
entirely from the web app and chat*. Viewing is built: every process is drawn live in the web
app, and the chat answers with the same text. Creating rests on UC-4.1, *a process from a
description*. Changing by a person and rolling back have no requirement of their own. The roadmap
names them *pair editing with rollback*, and the blueprint of Taktus's own development asks the
web app for *pair editing*. Neither says what that must achieve or how it is checked.

A *use case* is one file that says what a capability must achieve, how that is checked, and what
it does not have to do. Code is held to it by tests. The session has written one: UC-4.15, *a
person changes a process in dialogue, and rolls it back*. This request asks you to accept it.

What was attempted: the tasks of this track were to be written from an existing use case, as every
task is. The nearest are UC-4.1, which builds a new process from a description and ends when it is
commissioned, and UC-4.3, which is the change Taktus makes on its own and says in its boundary
that a person's change *is pair editing (roadmap `0.3.0`)*. Neither states a condition a person's
change could be held to.

## 2. Why you are being asked

Entry M3.15 of `docs/decisions/anchors.taktus.md`: what a use case requires is yours, and this
adds one.

**Sources checked:** `docs/vision/` — principle 1 (an orchestrator), 2 (AI at the core), 6 (no bus
factor of zero), 10 (the autonomy range, with guardrails) and 13 (no lock-in) give the direction,
and the non-goal *not a visual block builder* rules out dragging blocks; none states the
conditions, so this is not a restoration (M2.7). The ADRs — ADR-0030 (the rehearsal), ADR-0008
(reading an answer back), ADR-0026 (the autonomy statement) and ADR-0035 (the active version) say
how the parts work, not what a person's change must achieve. Both anchor pages — M3.15 makes the
requirement yours. The register — DEC-0124 and DEC-0175 asked the same question for UC-4.14 and
UC-1.9, use cases a task needed and no step of the migration wrote; you answered both with the
use case as written. That is the precedent this recommendation follows; it does not decide for
you.

## 3. What you must decide

Whether UC-4.15 states what changing a process from the web app and chat must do, as written.

## 4. What you need to know to decide

**Words used here.** A *process version* is one registered state of a process; the *active*
version is the one that runs. A *proposal* is a changed version Taktus works out from what a
person asked for, not yet registered. A *rehearsal* is a run in which nothing leaves the system:
what would be sent out is answered from a recording of the last real call (ADR-0030).
*Commissioning* is the person's explicit act that makes a proposal the active version.

**What UC-4.15 requires**, in short (the file is
`docs/usecases/process/UC-4.15-a-person-changes-a-process-in-dialogue-and-rolls-it-back.md`):

| Condition | Where it comes from |
|---|---|
| a request in the person's own words becomes a proposal, shown as its difference against the active version, step by step with method, reason and class; nothing changes yet | the roadmap's *pair editing*; CLAUDE.md §3 |
| a proposal that would not register is not offered, and the person is told what is missing | the registration the process component applies to every version |
| the proposal is rehearsed before it can be commissioned, and the person sees what it did | UC-4.1, which asks the same of a new process; ADR-0030 |
| only commissioning registers it; the act is in the ledger with who did it; a free-text "yes" is read back first | UC-1.2; ADR-0008 |
| a raise of the autonomy level still needs its approval; no check is skipped | ADR-0026 |
| rolling back is one act: an earlier version becomes current again as a new version, nothing deleted | UC-4.3, which states the same for Taktus's own changes; CLAUDE.md §9 *never delete* |
| the same from the web app and the chat | the roadmap's completion criterion |
| only an identity that may register versions of the process | UC-7.3 is not built; until it is, the rule registration applies today |

**What it does not require**, in its boundary: a visual builder; Taktus's own changes (UC-4.3);
a new process from nothing (UC-4.1); the bundle format (ADR-0011); rights per role (UC-7.3);
merging two proposals.

**How it would be built**, so that you can see the cost. ADR-0091, written with this request,
makes the proposing itself a process of Taktus's own. A language model reads the request and
proposes the changed version; that is the variable part. Rules then validate it, compute the
difference and rehearse it. Commissioning and rollback are rules, and are the person's acts. The
web app and the chat call the same surface.

**What it commits the project to.** The tasks of this track are held to these conditions and
cannot loosen them. Changing one later is a request of its own.

## 5. Options

### Option A — UC-4.15 as written, in `0.3.0` (recommended)

- **Meaning:** UC-4.15 is in force with the conditions above; the track's tasks are written from it.
- **Consequence:** `0.3.0` is complete only once a person can change and roll back a process from
  both the web app and the chat, with a rehearsal before every commissioning.
- **Effort:** none now; in `0.3.0`, the larger part of the remaining work.
- **Reversibility:** cheap until the first task of the track is merged; afterwards a change is a
  request for this use case.
- **Why recommended:** every condition comes from a decision already in force or from the
  roadmap's own completion criterion, none moves a limit or an autonomy level, and where two
  readings were possible the stricter was taken — the rehearsal before every commissioning.

### Option B — UC-4.15 without the rehearsal before commissioning

- **Meaning:** a proposal may be commissioned without a rehearsal; the person sees the difference
  and decides on it alone.
- **Consequence:** less to build in `0.3.0`; a change that breaks a run is found by the first real
  run instead of by the rehearsal.
- **Effort:** none now; in `0.3.0`, perhaps a quarter less.
- **Reversibility:** cheap; the rehearsal can be required later by a request.

### Option C — no use case; `0.3.0` keeps its criterion unspecified

- **Meaning:** UC-4.15 is withdrawn. The track is built against the roadmap's wording alone.
- **Consequence:** nothing checks what *changed and rolled back* means.
- **Effort:** none.
- **Reversibility:** cheap now; costly once the track is built.

## 6. What is blocked

Nothing: the provisional answer is in force, and the track is built against UC-4.15 as written. If
no answer arrives by 2026-10-26, it stays so, and changing a condition afterwards costs a request
for that use case instead of one edit now.

## 7. How to answer

"DEC-0186: Option A.", "DEC-0186: Option B." or "DEC-0186: Option C." in issue [#293](https://github.com/Jersyfi/taktus/issues/293).
A free-text answer is read back as an interpretation and confirmed before it is acted on.
