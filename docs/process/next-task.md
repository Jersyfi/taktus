# The standing brief: continue with the next task

What a session does when the owner says only "continue with the next task". It replaces the
briefs the owner wrote by hand for every task (DEC-0051). Each step is what one of Taktus's
development processes will do once it runs them itself: P-01 keeps the backlog, P-02 makes a task
ready, P-03 implements it (`docs/process/README.md`).

**The repository wins over this page.** Where this page and a rule elsewhere disagree, that is a
documentation defect: correct it and record it (M1.4).

## 1. Read

1. `CLAUDE.md`, all of it.
2. `docs/status.md`: where the project stands.
3. `docs/decisions/anchors.md` and `docs/decisions/anchors.taktus.md`: which questions are yours
   and which are the owner's.

## 2. Record every answer first

Before any other work, record every answer the owner gave in an issue since the last session.
`make backlog ANSWERS=1` lists the owner's comments on the issues of every open request.

- A decision request answered: its file moves from `docs/decisions/open/` to `docs/decisions/`
  with its `## Outcome`, and every place the answer changes is encoded.
- A need provided: its file moves with its `## Outcome`, and section 7 of the need is run to
  confirm it.
- A free-text answer is not acted on silently: the interpretation is written back in the issue
  and confirmed first (ADR-0008).

The records go into the pull request of this session's task, as its first commit. Where the
answer has nothing to do with the task, they go into a pull request of their own, opened first.

## 3. Take the top ready task, and claim it

**A red `main` comes first.** When the newest `ci` run on `main` is red, or an open issue says
"main is red", mending it is the task, before anything below (ADR-0096 §5).

1. `git fetch origin` and start a branch from `origin/main`.
2. `make backlog NEXT=1` names the task: the top ready one that nobody has claimed and that
   is not handed to Taktus. **Never take an open issue labelled `to-taktus`**: it is Taktus's
   (DEC-0197). Never add or remove that label either; handing a task over is the owner's.
3. **Claim it before working on it**: add the label `in-progress`, and comment "Claimed by
   <branch>." on the issue.
4. Read the issue again. If an earlier claim comment by someone else is there, theirs wins: remove
   your comment, leave the label, and take the next task.

**If none is ready**, `make backlog NEXT=1` names the top task that is not, with what it lacks.
Make it ready: write the missing sections from the source the issue names, as P-02 would; then,
as a person does, set the milestone and the priority and add `ready` (P-02 adds no label, issue
#70; P-01 reports a wrong one and changes none, issue #71). Where a section cannot be written from the
repository, the task stays unready and the issue says what is missing; take the next one.

**Never invent work outside the backlog.** Something found on the way that is not the task becomes
an issue, in the shape of the form `Task`, and stays for its turn.

## 4. Do it: one issue, one pull request

- One pull request, targeting `main`, whose description closes the issue (`Closes #N`).
- The whole of `CLAUDE.md` applies: the definition of done (§11), the anchors (§8), the records
  (§9). A requirement is met, or its failure is argued in a decision request. It is never
  adjusted to become meetable.
- A spend on the owner's credential to derive or verify a fact is allowed up to USD 1 for the
  whole task, recorded as a notice; beyond that it is a request (M2.8).
- A change of what the software does inside the issue's scope (M2.4) is a line of the
  description's section *Behaviour changes* — old behaviour, new behaviour, reason — and no
  notice file (DEC-0189 rule 2). Every other mode-2 decision is still a notice.
- **Merge when the pull request is green**: `make gates` locally, and every check in CI. The
  session merges its own pull request once every check is green, with no more running in
  parallel than CI carries, and never one that raises a `BLOCKING` request (M1.22, DEC-0189).
  Once #390 lands, the pull request stays a draft until `make verify` passed for its pushed head,
  and CI runs from *ready* on (ADR-0096 §4).

## 5. Sessions in parallel

- Claim before working; skip a claimed task, and a task labelled `to-taktus`.
- Numbers of records — `DEC`, `NTC`, `NEED` — are reserved before the record is written:
  `make reserve KIND=NTC` prints a number no other session holds. Write the record under it and
  name it anywhere at once; it is never renumbered. A number taken by hand fails CI
  (DEC-0189 rule 6).
- The register's index is not edited: `make register` prints it from the records. Before the
  final push, `git fetch origin main` and rebase as for any change.

## 6. Report

The pull request is the report. Its description has the shape CI checks (ADR-0017 §7): what this
is about, the decisions it raises by ID and category, every change of what the software does
inside an agreed scope as a line of *Behaviour changes* (M2.4, DEC-0189 rule 2), what was done,
why this way, what to check, and last the section *Needed from the owner*, which is the output of `make status`. The
`owner-list` workflow writes it from the branch's register; a description opened without it
gains it on its first run (DEC-0189 rule 1).

The message that ends the session says, in a few lines: the issue and the pull request, whether
CI is green, every record raised by ID, and what the owner must answer or provide — each with its
issue, where the owner answers.

## When this page is retired

When Taktus runs P-01, P-02 and P-03 on its own instance (`docs/roadmap.md`). Until then it is
kept current like any other rule: a change in how a session works changes this page in the same
pull request.
