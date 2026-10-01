# ADR-0028 — What the owner must act on becomes a record: needs requests and the status report

**Status:** accepted · amended 2026-09-30 (DEC-0021): which changes change the state · extends ADR-0017 with a fifth record kind and a status report the owner
does not have to ask for · amended 2026-09-29 by DEC-0026 and DEC-0027: the status file
stores neither the generated list nor a line every pull request rewrites (§3)

## Context
Pull request #1 buried four open questions at the end of a long description, and the owner could
not act on them. ADR-0017 fixed that for *decisions*: a blocking decision keeps the pull request
a draft and becomes an issue assigned to the owner. It fixed it for decisions and for nothing
else.

The same failure has now happened with something that is not a decision. Pull request #10
built the coding worker and stated, in a note, that a live run needs a credential — an API key
or a subscription token — which no session may capture. Pull request #13 repeated the note and
named the three credentials the first end-to-end run needs. The owner had asked explicitly to
be told when such a thing is needed, and to be given the steps. The information never reached
him. A note in a pull request description is read by a reviewer of the diff, once, and is gone
with the pull request. The owner does not know where the project stands.

Two things are missing, and both are the same shape as the decision request was before
ADR-0017: something the owner must act on has no record and no channel.

1. **A need.** The work needs something only the owner can provide: a credential, an account,
   access to a system, a purchase, an action on a server, information about an environment.
   That is not a decision — there are no options to choose from — and it is not a note, because
   something must happen. Today it has no place. Decision requests exist (mode 3 of the anchor
   page); notices exist (mode 2); a need has neither a template, nor a gate, nor an issue.
2. **The picture.** The owner receives decision requests but never the picture they belong to:
   where the project is against the roadmap, what comes next, what is blocked, what is promised
   and not yet kept. Each pull request describes its own delivery; nothing describes the state.
   The roadmap says what a milestone must reach, and its "done so far" paragraph has grown
   into a list of what pull requests delivered — claims, not a checked state.

## Decision

### 1. The needs request, a fifth kind of record
A **needs request** is the record of something only the owner can provide. It is the fifth kind
of record in the register `docs/decisions/`, beside the decision request, the decision record,
the DEFECT record and the notice. Its identifier is `NEED-NNNN`, in a sequence of its own.

**The timing rule is the point.** A need is raised when it becomes *foreseeable*, not when it
blocks. A pull request that builds something whose real use will need a credential, an account
or an access raises the need in that pull request, with a date by which it is needed. Waiting
until a run fails for lack of it is too late: by then the owner has lost the weeks in which he
could have provided it, and the session that meets the failure is not the one that knew the
steps.

**Which mode governs it.** Raising a need is mode 2 of the anchor page: the session decides
that a need exists and raises it, and nobody approves the raising. Entry M2.5 of
`docs/decisions/anchors.md` and of `anchors.taktus.md` says so. The record of that mode-2
decision is the needs request itself, not a notice. Providing the need is the owner's, and
nothing else: the owner is not asked to decide anything, only to act, with the steps in hand.

**The shape.** One Markdown file with a header and seven sections, none empty, no placeholder.
`docs/decisions/TEMPLATE-NEED.md` is the template; `.github/ISSUE_TEMPLATE/needs-request.yml`
mirrors it. Header: `**Kind:**` (one of `credential`, `account`, `access`, `purchase`,
`action`, `information`) · `**Raised in:**` · `**Issue:**` · `**Needed by:**` (a date) ·
`**Foreseeable since:**` (the pull request in which the need became foreseeable, which is
where it should have been raised).

| § | Section | Content |
|---|---|---|
| 1 | What is needed | in plain words, for a reader who has read nothing else |
| 2 | Why | what it unlocks, and which milestone or task depends on it |
| 3 | By when | the date, and what happens if it is not there by then |
| 4 | How to provide it | the steps, where it goes, which permissions and scope, how long it is valid; the literal commands where there are any |
| 5 | What it must never be | never pasted into a chat, never committed, never sent to a session; where it goes instead |
| 6 | What happens next | once it is in place: what to tell the session, or what runs on its own |
| 7 | How to confirm | that it was provided correctly, without revealing it |

Section 5 is not optional and not boilerplate. The repository is public and a session never
receives a secret value (CLAUDE.md §9, `CREDENTIALS.md`). A needs request that asks for a value
to be pasted anywhere a session can read it is wrong, and the gate cannot tell — the reviewer
can, and section 5 is where to look.

**Where the files live.** `docs/decisions/open/NEED-NNNN-<slug>.md` while the need is open;
`docs/decisions/NEED-NNNN-<slug>.md` once provided, with an `## Outcome` section — the date it
was provided, how it was confirmed (section 7, executed), and the pull request that recorded
it. Every provided need is listed in the register index. An open need has a GitHub issue
labelled `needs-owner`, assigned to the owner, with the same content; the file names the issue.

**A need does not keep a pull request a draft.** The blocking test of ADR-0017 §3 is about
work that must be thrown away; a missing credential does not make the work that needs it
wrong, it makes it unproven. The pull request merges; the need stays open until provided; the
status report (§3) carries it until then.

### 2. The credential coverage gate
Every credential the software reads is a parameter described in `CREDENTIALS.md` — that has
been the rule since the first commit. From now on every row of that register also names the
needs request under which the owner provides the parameter, or states `none` with the reason
nobody has to provide it (generated by the deployment, created by the CI service per run,
optional and unused).

`make gate-decisions` fails when: a needs request misses a section, keeps a placeholder, cites
a kind outside the vocabulary or names no issue; a provided need lacks its outcome or its index
entry; a row of `CREDENTIALS.md` names no needs request and gives no reason; a needs request a
row names has no file; or the code names a credential file variable
(`<NAME>_FILE`) that `CREDENTIALS.md` does not describe. The last check is what turns
"a pull request builds something whose real use depends on a credential that has no needs
request" into a failure: the new variable forces a row, and the row forces a need or a reason.

### 3. The status report
`docs/status.md` is one file that says where the project stands and what is needed from the
owner. It has five sections in a fixed order: where the project is against the roadmap — the
current milestone, what of it is done and what is not; the next two or three pull requests and
why in that order; what is needed from the owner, by when, the most urgent first; what is
blocked, and on what; the promises not yet kept — tests pending, limits documented rather than
enforced, anything marked provisional.

Facts only. No forecast dressed as a fact, no "almost done". Where something is unknown, the
file says it is unknown.

Section 3, *Needed from the owner*, is generated and **not stored**:
`tools/check_status.py --print` (`make status`) prints it from the open needs and decision
requests of the register, sorted by the date each is needed. The file's section 3 says where
the list is — the pull request description, `make status`, and the open issues labelled
`needs-owner` or `decision-request` — and holds no copy of it. The other four sections are
written by hand by the pull request that changes the state.

*Amended 2026-09-29 (DEC-0026).* Until then the list was written into the file by `make
generate`. A generated list in a committed file is edited by every pull request that touches
the register, so any two such pull requests conflict on it, and whichever merges first makes
the other's copy stale. That happened to all four pull requests of 2026-09-23 at once.

**Every pull request that changes the state of the project updates the file**, and
`make gate-status` fails when it did not: when a change under `src/`, `workers/`, `blueprints/`,
`contracts/`, `deploy/`, `migrations/`, `tools/`, `docs/roadmap.md`, `docs/adr/` or
`docs/decisions/` reaches the base branch without a change to `docs/status.md`; when section 3
stores a list instead of saying where it is; when the file carries a line every pull request
rewrites — a stored date, or a running list of what was decided since the last version; when a
section is missing, empty, out of order or keeps a placeholder; when the milestone named in
section 1 is not a milestone of the roadmap.

*Amended 2026-09-30 (DEC-0021).* The owner answered which changes change the state of the
project: **a pull request that touches a milestone item, a need, a decision or a contract
updates the file; one that fixes a defect does not.** The gate therefore counts a change to
`docs/roadmap.md`, to a record under `docs/decisions/` or an ADR under `docs/adr/`, or to a
file under `contracts/` — and not the record of a documentation defect, and not a change to
code, tools, workers, blueprints or the deployment on its own. Until then every change under
`src/`, `workers/`, `blueprints/`, `deploy/`, `migrations/` and `tools/` counted too, and the
first pull request Taktus opened had to write a status line about a tool it had taught to name
`git` (DEC-0021 §4).

*Amended 2026-09-29 (DEC-0027).* Until then the file carried an `As of` date that the gate held
to the newest record of the register, and a paragraph listing what had been decided since the
last version. Every pull request rewrote both, so any two conflicted on them even after the
generated list had left the file. The date of the status is the date of its last commit; what
was decided when is the register's index. A record the status has not accounted for is still
caught, because every record lives under `docs/decisions/` and a change there counts as a change
to the state.

**The pull request description carries the list.** Its last section, `## Needed from the
owner`, is what `make status` prints for that branch, so that the owner sees what is needed
without opening a file. CI generates the list from the branch's register and fails when the
description differs from it. The description is the one place the list is carried: it
belongs to one branch and is never merged with another.

### 4. The working rule
CLAUDE.md §9 gains the rule that this ADR exists for: **a note in a pull request is not a
message to the owner.** Anything the owner must act on — a decision, a need, a date — becomes a
record and an issue assigned to him. Never only a line in a description.

## Alternatives
- **Raise a need as a decision request.** It has no options; the seven sections of a decision
  would be filled with a single answer, and the owner would read a recommendation where he
  needs steps. The shape is different because the act is different.
- **Raise a need as a notice.** A notice records a decision nobody approves and asks for
  nothing. A need asks for an act. The owner does not read notices; that is what mode 2 means.
- **A `needs` section in the pull request template, no file.** That is the note that failed.
  A section in a description is still a description.
- **Generate the whole status file.** The milestone's state, the order of the next pull
  requests and the promises not kept are judgements, checked against the tree by the person
  or session writing them. A generator would produce a list of files. Only the section that is
  a list of records is generated.
- **Check freshness by date alone.** A date is touched without the content being true. The
  gate checks what it can — the touch, the generated section, the milestone name, the date
  against the register — and the reviewer checks the rest.

## Consequences
- A pull request that builds something needing a credential costs one more file and one issue.
  That is the price of the owner learning it in time, and it is paid by the session, not the
  owner.
- The owner has one file to open. What it asks of him is in every pull request description,
  with a date, and one click from the file: the open issues labelled `needs-owner` or
  `decision-request`. Since DEC-0026 the file points at the list rather than holding it.
- The three needs that were overdue when this ADR was written — the coding agent's credential,
  the repository connector's token, the model endpoint's key — and the platform's interface
  note are raised in the same pull request, with `**Foreseeable since:**` naming the pull
  request that should have raised them.
- `CREDENTIALS.md` gains a column, and the coverage check means a credential can no longer be
  added to the code without a row and a need.

## Where this promise ends

The gate checks shape and presence: sections, dates, that section 3 points at the list and
stores none, a row per credential variable, an index entry. It cannot check that the steps of a needs request work,
that its date is right, or that the rest of the status file is true; a reviewer can, and the
owner will notice when he follows the steps. The coverage check finds credential variables by
their naming convention, `<NAME>_FILE`, in the code directories; a credential read under
another convention, or by a test, is not seen. The freshness check
of the status file sees a *touch*, not a truthful update. The issue is created by the session
with the repository's tooling; a repository hosted elsewhere needs its equivalent. Nothing here
makes the owner provide what is asked; it makes sure he knows. The list lives in pull request
descriptions and in the issue tracker, not in the file: an owner who reads only the file sees
where the list is, not the list. The file carries no date of its own: a reader of the file
alone learns how current it is from the date of its last commit, which the host shows beside it,
not from the text.

Since DEC-0021 the gate sees the four kinds of file that change the state, and not a milestone
item completed in code alone: a pull request that finishes an item without touching the
roadmap, a record, an ADR or a contract passes it, and its description is where a reviewer
checks whether the status should have moved.
