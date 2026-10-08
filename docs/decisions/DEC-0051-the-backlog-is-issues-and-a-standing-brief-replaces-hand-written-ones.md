# DEC-0051 — The backlog is issues, and a standing brief replaces hand-written ones

**Category:** NON-BLOCKING
**Raised in:** the brief of 2026-10-07, after the audit of 2026-10-01 measured what hand-written briefs cost; recorded in [#59](https://github.com/Jersyfi/taktus/pull/59)
**Issue:** none; the owner decided in the brief before a request was written, and this record is the question with the answer
**Needed by:** 2026-10-07
**Written after the answer:** the owner answered in the brief of 2026-10-07; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

Until now every task reached a session as a brief the owner wrote by hand in a chat. The audit of
2026-10-01 measured the cost. Briefs caused requests: a brief that contradicted the repository
turned into a question. And the owner's answers reached the repository one to seven days late,
because they waited in a chat for the work they belonged to.

Once Taktus develops itself, nobody writes briefs. Its own processes keep the backlog (P-01
Roadmap control), make a task ready (P-02 Refinement) and implement it (P-03 Implementation).

## 2. Why you are being asked

How work on the project is organised is how the owner directs it; the anchors give the session the
order of work inside an agreed scope (M1.2) but not the source of the work.

**Sources checked:** the vision (principle 1, an orchestrator and no parallel register), the ADRs
(ADR-0017 on what reaches the owner, ADR-0028 on needs), both anchor pages (M1.2, M1.7) and the
register (DEC-0026 on what may be stored, DEC-0040 to DEC-0043 on late answers). None says where
the next task comes from.

## 3. What you must decide

Where a session takes its next task from, and in what shape.

## 4. What you need to know to decide

- **Ready.** A task a session can carry out without asking: what must be achieved, how it is
  verified, where the boundary lies, its milestone and its component.
- **Claimed.** A task a session has started; a second session skips it.
- **The standing brief.** One file in the repository that says what a session does when the owner
  says only "continue with the next task".

## 5. Options

### Option A — issues as the backlog, a standing brief, the shape of P-01 to P-03 (recommended)

- **Meaning:** the backlog is the repository's issues, in milestones matching the roadmap. An
  issue is ready when it carries the three sections of a use case, its milestone and its
  component; the issue template asks for them. Labels `ready`, `in-progress` (which claims an
  issue) and a priority. Order: earliest milestone, then priority, then issue number. An issue
  blocked by an open need or decision is not ready and names what blocks it.
  `docs/process/next-task.md` is the standing brief; the owner answers in the issue itself, with
  the literal sentence the request offers, and the next session records the answer first. When
  Taktus runs P-01, P-02 and P-03 on its own instance, the standing brief is retired; the issues,
  the ready standard and the order stay.
- **Consequence:** a task needs no chat; an answer needs no chat. Taktus taking over changes who
  executes, not how the work is organised.
- **Effort:** the template, the labels, the milestones, the brief, and the backlog built once by
  hand.
- **Reversibility:** cheap.
- **Why recommended:** the owner's answer, below.

### Option B — briefs by hand, as before

- **Meaning:** every task arrives as a brief in the owner's chat.
- **Consequence:** the costs the audit measured continue, and nothing of it carries over to
  Taktus's own processes.
- **Effort:** none.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing.

## 7. How to answer

"DEC-0051: Option A." or "DEC-0051: Option B."

## Outcome

**Decided:** 2026-10-07
**Answer:** Option A, as the owner gave it. The backlog is GitHub issues, with milestones matching
`docs/roadmap.md`. An issue is ready when it carries the same three sections as a use case — what
must be achieved, how it is verified, where the boundary lies — plus its milestone and component,
and the issue template asks for them. Labels: `ready`; `in-progress`, which claims an issue; a
priority label. Order: earliest milestone, then priority, then issue number. An issue blocked by
an open NEED or DEC is not ready, and names what blocks it. `docs/process/next-task.md` is the
standing brief, and CLAUDE.md points to it. The owner answers in the issue itself, with the
literal sentence the request offers; the next session records it first. The backlog is built
once by hand, as P-01 would. When Taktus runs P-01, P-02 and P-03 on its own instance, the
standing brief is retired; the issues, the ready standard and the order do not change.
**Reasoning given:** briefs caused requests, and answers reached the repository one to seven days
late. Principle 1: no parallel register — the repository connector already reads issues.
**Recorded in:** [#59](https://github.com/Jersyfi/taktus/pull/59): `docs/process/next-task.md`, `.github/ISSUE_TEMPLATE/task.yml`,
`tools/backlog.py` (`make backlog`), CLAUDE.md §9, `docs/roadmap.md` (the retirement), and the
backlog as issues in the milestones `0.1.0` to `1.0.0`.
