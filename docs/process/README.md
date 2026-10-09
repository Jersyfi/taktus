# How work is organised

The work on this repository comes from one backlog, and it is organised exactly as Taktus's own
development processes will organise it (`blueprints/dev-orchestration/`): **P-01 Roadmap control**
keeps the backlog, **P-02 Refinement** makes a task ready, **P-03 Implementation** turns a ready
task into a pull request. Until Taktus runs those three on its own instance, a session does by
hand what they will do, following the standing brief, [next-task.md](next-task.md). When Taktus
takes over, who executes changes; nothing on this page does (DEC-0051).

## The backlog is the repository's issues

There is no second list. Principle 1 forbids a parallel register, and the repository connector
already reads issues. An issue labelled `decision-request` or `needs-owner` is not work: it is a
question or a need waiting for the owner (`docs/decisions/`). Nor is an issue labelled `report`:
it carries a process's reports.

**Milestones** are the versions of `docs/roadmap.md`, `0.1.0` to `1.0.0`, with the same names.
Which feature lands in which milestone is the session's (M1.7); the roadmap says it, and the
issue's milestone follows it. **Each item of a milestone names the issues that carry it**, as
`#N`, so that the two can be held against each other by a rule (NTC-0049).

**P-01 Roadmap control** does that, and runs as a bundle
(`blueprints/dev-orchestration/processes/P-01-roadmap-control.yaml`). It reports, as a comment
on one issue labelled `report`, every item that names no issue, every open issue in a milestone
whose items do not name it, and every issue labelled `ready` whose content fails the standard
below; and it prints the backlog in its order. It proposes; a person names the issue in the
roadmap, sets the milestone or removes the label (issue #71).

## Ready

A task is **ready** when it carries:

1. **What must be achieved** — the outcome, not the route;
2. **How it is verified** — the condition that must hold, so that it cannot be met by
   interpretation;
3. **Where the boundary lies** — what is not part of it;
4. its **component**, and the **source** it comes from;
5. its **milestone**, and exactly one **priority** label;
6. **"Blocked by"**: every `NEED-NNNN`, `DEC-NNNN` or issue it waits for, or `nothing`.

The first three are the sections of a use case (`docs/usecases/TEMPLATE.md`), so that a task and
a requirement are read the same way. The issue form `Task` asks for all of them; whoever triages
sets the milestone and the priority. **A task blocked by an open need, decision or issue is not
ready**, and says what blocks it.

The label `ready` says that someone judged the issue's content to meet the standard — points 1
to 5. Whether what it names under "Blocked by" is still open is checked when the backlog is read,
not by the label: a blocked task keeps its label and is offered as soon as its blocker closes.
`make backlog` checks both: it lists every issue labelled `ready` that fails the standard or is
blocked, with the reason, and never offers it as the next task.

The standard is written once, in `src/taktus/components/run/domain/service/ready.py`. A section
runs to the next heading or to a horizontal rule (`---`); a footer after the rule — the record or
pull request the issue was written under — is part of no section and blocks nothing (DEC-0116).
`make backlog` runs it, and so does P-03 Implementation's admission, which also refuses a
claimed issue and claims the one it admits with `in-progress`. P-02 Refinement uses it to find
the sections an issue lacks, writes those as a comment, and adds no label (issue #70).

## Labels

| Label | Means |
|---|---|
| `ready` | the task's content meets the ready standard; blockers are checked when the backlog is read |
| `in-progress` | a session has claimed the task and works on it; every other session skips it |
| `priority:high`, `priority:normal`, `priority:low` | the order within a milestone; exactly one per task |
| `task` | an issue made from the form `Task` |
| `report` | the issue carries a process's reports, such as P-01's; it is not work |

## Order

**Earliest milestone, then priority, then issue number.** `make backlog` prints the backlog in
that order; `make backlog NEXT=1` prints the one task a session takes next. The order is written
once, beside the standard (`backlog()` in the same module); P-01 prints it from the same code.

## Where the owner answers

In the issue itself. A decision request offers a literal sentence ("DEC-NNNN: Option A."), a
needs request one too ("NEED-NNNN is provided."); the owner writes it as a comment on the
request's issue. No answer needs to pass through a chat. The next session records it first,
before any other work (CLAUDE.md §9); `make backlog ANSWERS=1` lists the owner's comments on the
issues of every open request.

## When the standing brief is retired

When Taktus runs P-01, P-02 and P-03 on its own instance, [next-task.md](next-task.md) is
retired (`docs/roadmap.md`, the handover path). The issues, the ready standard, the labels and
the order on this page do not change.
