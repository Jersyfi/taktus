# ADR-0017 — Decision requests as a repository mechanism

**Status:** accepted · operationalises ADR-0008 for this repository · amended by ADR-0021: the
category `DEFECT` is read as *documentation defect*; a wrong result is a *result defect* ·
amended 2026-09-21: the anchor list has four modes in two files (§1), and a mode-2 decision
has a record type, the notice (§2a) · amended 2026-09-21 by DEC-0014: every notice carries a
kind, and a behaviour change inside an agreed scope is a notice (§2a) · extended by ADR-0028: a fifth record kind, the needs
request `NEED-NNNN`, for what only the owner can provide, and the status report
`docs/status.md` · amended 2026-09-29: every pull request description states what the change is
about, what was done, why that way and what to check (§7) · amended 2026-10-01 (DEC-0039): what
fits no entry is decided in the direction of the vision (§1a), the derivability test, the
register as precedent and the acceptance rate (§9) · amended 2026-10-01 (DEC-0040 to DEC-0042):
a decision states how it follows its source, restoring a use case is mode 2 (§1a), the override
rate is reviewed and counts only what was asked before it was answered (§9)

## Context
ADR-0008 defines the decision request: the planned question about direction, with a fixed shape,
raised when work reaches an anchor. It describes the product. This repository is also run by that
product's own rules, and until now nothing said how a decision request looks *here* — as a file, a
pull request, an issue.

Pull request #1 showed the cost. Four open items sat at the end of a long description, written for
a reader who had just read the diff. The pull request was merged with all four unanswered. Five
defects, all in the mechanism rather than in the work:

- (a) nothing made an unanswered blocking question prevent a merge;
- (b) the questions assumed context the reader did not have — no background, no explanation of
  terms, no statement of what was being committed to;
- (c) one item was not a decision at all but an internal placement inside a planned refactor;
- (d) one item was a defect in the repository's own documents and was escalated as a choice between
  two readings instead of being corrected;
- (e) nothing stated concretely which questions belong to the owner, so every session guessed
  again.

## Decision

### 1. The anchor list
Two files, because they are two different things. `docs/decisions/anchors.md` is the shipped
default: the anchor configuration a new tenant inherits, written as a template — product.
`docs/decisions/anchors.taktus.md` is the configuration of the tenant that is the Taktus
project: the owner's own answers — not product. A question is tested against the tenant's page
before it is raised. It fixes defect (e).

Both pages sort every question into one of **four modes**: (1) the operator decides, no notice;
(2) the operator decides and records a notice (§2a); (3) the operator prepares a worked opinion
and the owner decides — a decision request in the shape of §4; (4) the owner decides and the
operator supplies data. The first version of the page had two lists, the owner's and the
session's; the owner's answers of 2026-09-21 fell almost entirely between them. The same entry
may sit in a different mode per tenant — a change to an accepted ADR is the owner's in a
managed product and the session's in this project while the vision holds — and the entries of
a page are identified (`M3.7`) so that a request can cite one and a tenant can move one.

### 1a. What fits no entry is decided in the direction of the vision

*Amended 2026-10-01 (DEC-0039).* Until then a situation that fit no entry of the anchor page
became a `NON-BLOCKING` decision request that proposed its mode. In a young project almost every
situation is new, so that rule generated questions by design: a non-blocking question costs the
session nothing and the owner reading time.

Now a situation that fits no entry is **decided by the session in the direction the vision and
the existing anchors point**, and recorded as a notice of kind `unlisted` (entry M2.6) that names
those sources and, in its section 5, the entry it proposes for the anchor page. A question is
raised only where the vision gives no direction. Entries of mode 3 and mode 4 are untouched.
The owner overrides a notice that went the wrong way with a decision; the notice then names it
in `**Overridden by:**`.

*Amended 2026-10-01 (DEC-0040, DEC-0041).* **A decision follows its source.** The session decides
according to the source it cites, and the notice states, in `**How it follows:**`, how the
decision follows from it; naming a source is not following it. Where two options are both
consistent with the sources: strict in substance, sparing in ceremony. The gate checks that the
statement is there; whether it holds is for review. **Bringing a use case up to the owner's own
definition** — an amendment that only restores what `docs/vision/` and the owner's project
definition already require — is decided by the session and recorded as a notice of kind
`restoration` (entry M2.7); a new requirement stays mode 3.

**The derivability test.** Before raising any decision request, the session checks the vision,
the ADRs, both anchor pages and the register. The request names the sources checked and why
none of them answers it, in `**Sources checked:**` in its section 2; a request without it is
returned, and the gate of §8 fails it (from DEC-0039 on).

### 2. Defects are corrected, not escalated
When the repository's own documents are ambiguous, contradict each other, or turn out to be wrong,
that is a **documentation defect**, not a decision. The session corrects it in the same pull
request — as an ADR amendment where an ADR is involved — and records it under `docs/decisions/`
as a DEFECT record:
what was wrong, why it was wrong, what it now says, and what changed in substance. The owner is
never presented with a choice between two readings of a document that should not have been
ambiguous. It fixes defect (d).

One exception: if the correction would change what the software actually does, not only how it is
described, the change is a decision and follows §3.

### 2a. Mode-2 decisions are recorded as notices
A decision the session makes alone and merely reports has, until now, no record type: it became
a note in a pull request and disappeared with it. A decision of mode 2 — restructuring
documentation, changing a test strategy, weakening a gate where it is demonstrated to have no
value, changing what the software does inside an agreed scope without breaking a contract,
moving a limit or saying anything public — is recorded as a **notice**:
`docs/decisions/NTC-NNNN-<slug>.md`, in the register beside the decision records, with what was
decided, the evidence it rests on, what was considered, and which mode-2 entry of
`anchors.taktus.md` permits it. Nobody approves a notice; that is what mode 2 means.
`docs/decisions/TEMPLATE-NOTICE.md` is the template.

Every notice carries a **kind** in its header, and the register index shows it. The kinds are
a vocabulary the shipped default defines (`anchors.md` §1): `restructuring`, `test-strategy`,
`gate-weakened`, `behaviour-change`. Every mode-2 entry names its kind; a notice carries the
kind of the entry it cites, and the gate of §8 fails on a mismatch. The kind exists beside the
entry because an entry is one tenant's permission — it may be moved, split or renumbered —
while the kind means the same in every tenant: a register is read by kind, and a weakened gate
is found among any number of behaviour changes. This is the owner's answer to DEC-0014, the
first question raised under *Neither list*.

A notice of kind `gate-weakened` — a gate weakened or removed, entry M2.3 here — additionally
requires, in the record itself, the section *Why the gate had no value*: what the gate looked
at, what it would have caught, the evidence that it caught nothing and could catch nothing. "It
was in the way" is not evidence. The gate of §8 checks the shape and that the section names a
gate; it cannot check the truth of the demonstration, and the reviewer can.

### 3. Four categories
Everything a pull request wants to tell the owner falls into exactly one of these.

| Category | Meaning | Where it appears | Effect on the pull request |
|---|---|---|---|
| **DEFECT** | a documentation defect: the repository contradicts itself or is wrong | corrected in the pull request; a DEFECT record under `docs/decisions/` | none |
| **NOTE** | information the owner should have; nothing to answer | the "Notes" section of the description; never phrased as a question | none |
| **NON-BLOCKING** | a choice is pending; work continues on a clearly marked provisional answer | a file under `docs/decisions/open/` and a GitHub issue labelled `decision-request`, assigned to the owner | may merge; the description names the decision by ID |
| **BLOCKING** | continuing would produce work that must be thrown away | a file under `docs/decisions/open/` and a GitHub issue as above | **stays a draft** until answered |

GitHub refuses to merge a draft. Defect (a) therefore becomes technically impossible rather than
merely forbidden. A CI job reads the draft flag and fails when a pull request names a BLOCKING
decision while not being a draft. Defect (c) is addressed by the NOTE category: information is
stated, never asked.

The category label `DEFECT` is short for *documentation defect* and is used only in the
register. Since ADR-0021 the product knows a second kind, the *result defect* — a run that
completed and reported success with a wrong result. The two are never confused because the
bare word is not used: it is always *documentation defect* or *result defect*.

**The blocking test.** A decision is blocking only if continuing would produce work that must be
thrown away. If a provisional answer can be marked and later changed cheaply, the decision is
non-blocking. Without this test everything drifts into blocking, and a blocking request that was
not necessary costs the owner attention that a real one will later lack.

**The comprehension test.** Could a person decide this who has read neither the diff, nor the
session, nor any ADR? If not, the request is not finished. This is the test #1 failed (defect (b)).

### 4. The shape of a request
Every request, open or answered, is one Markdown file with a header and seven sections. None of
the sections may be empty or hold a placeholder. `docs/decisions/TEMPLATE.md` is the template;
`tools/check_decisions.py` enforces the shape.

Header, one line per field:
`**Category:**` · `**Raised in:**` (the pull request) · `**Issue:**` · `**Needed by:**` (a date)
· for NON-BLOCKING additionally `**Provisional answer:**`.

| § | Section | Content |
|---|---|---|
| 1 | What this is about | the situation in plain sentences, without repository jargon |
| 2 | Why you are being asked | the entry of `anchors.taktus.md`, mode 3 or 4, that makes this the owner's call |
| 3 | What you must decide | exactly one answerable question |
| 4 | What you need to know to decide | every term explained; the background needed to judge; what the decision commits the project to |
| 5 | Options | two or three, each with concrete meaning, consequence, effort and reversibility; one marked recommended, with the reason — except in mode 4, where the question is the owner's own: the request names its entry in `**Mode entry:**` and marks no option recommended (anchors.md §1; DEC-0045, 2026-10-01) |
| 6 | What is blocked | what waits, a date by which an answer is needed, and what happens without one |
| 7 | How to answer | the literal sentence the owner can write back |

Section 4 is the one #1 lacked and the reason its questions could not be answered.

### 5. Where the files live and how they are numbered
- `docs/decisions/open/DEC-NNNN-<slug>.md` — an open request, BLOCKING or NON-BLOCKING.
- `docs/decisions/DEC-NNNN-<slug>.md` — a closed record: an answered request, a DEFECT record, or
  a question that was raised as a decision and reclassified as a NOTE.
- `docs/decisions/NTC-NNNN-<slug>.md` — a notice, the record of a mode-2 decision (§2a).
- `docs/decisions/README.md` — the register index; every record and every notice is listed there.
- Numbers are assigned once, in sequence, across open files and records, and never reused. A
  record keeps the number of the request it closes. Notices have a sequence of their own.

A plain NOTE gets no file: it lives in the pull request description. A question that was raised
as a decision and then reclassified gets a record, so that the register carries the precedent.

Order of work for a new request: test the question against `anchors.taktus.md` → write the file from the
template → open the issue from the issue template with the same content → put the issue link into
the file → name the decision in the pull request description → if BLOCKING, keep the pull request
a draft.

### 6. The return path
When an answer arrives, in whatever channel:

1. the answer, its date, the reasoning given, and a link to the pull request or issue are written
   into the file as an `## Outcome` section, and the file moves from `docs/decisions/open/` to
   `docs/decisions/` — the same commit deletes the open file and creates the record;
2. the record is listed in `docs/decisions/README.md`;
3. the issue is closed with a reference to the record;
4. a BLOCKING pull request leaves draft only then.

A free-text answer is never acted on silently (ADR-0008): the record states the interpretation,
and if the answer left room for more than one reading, the interpretation is confirmed with the
owner before the record is written.

### 7. Pull request description order
Fixed, in this order, given by `.github/pull_request_template.md`:

1. **What this is about** — the problem or the goal, in plain sentences.
2. **Decisions required** — either `None` or one line per decision: ID, title, category, issue.
   Near the top, never at the end.
3. **What was done** — what is different afterwards, as behaviour and as documents.
4. **Why this way** — the reason for this shape over the alternatives considered.
5. **What to check** — what the reviewer should look at, in order of risk.
6. Notes, if any — statements for the owner, never questions.
7. **Needed from the owner** — last, generated (ADR-0028).

Sections 1, 3, 4 and 5 are written for a reader who has not opened the diff. A description that
says "see the diff", or that lists files where it should say what changed, cannot be acted on
by the owner, who decides from the description.

*Amended 2026-09-29.* Until then the description had "What this delivers", the decisions and
"everything else". Pull request #38 — the first one Taktus opened itself — followed that shape
and still could not be acted on: its summary assumed the reader had read the diff. The four
sections make the missing parts explicit, and `tools/check_decisions.py` fails a description
without them, with one empty, or with them out of order.

The language is English throughout: the description, the issue, and every file under
`docs/decisions/`. An answer given in another language is recorded in English, with the original
quoted.

### 8. Enforcement
- `tools/check_decisions.py`, run as `make gate-decisions`, part of `make gates` and of CI. It fails
  when an open request misses a section or keeps a placeholder; when a decision named in the pull
  request description has no file; when a record lacks an outcome or a date; when a file remains
  under `open/` although its record exists; when a record is missing from the index. For
  notices: when the header lacks a mode-2 entry that `anchors.taktus.md` defines, a kind, a
  date or the pull request; when the kind is not the one the entry names on that page; when a
  section is missing, empty or out of order, or keeps a placeholder; when a `gate-weakened`
  notice lacks *Why the gate had no value* or that section names no gate; when a notice is
  missing from the index.
- The `decisions` CI job passes the pull request body and the draft flag to the same tool, which
  fails when a BLOCKING decision is named and the pull request is not a draft, and when the
  description lacks one of the four sections of §7 — about, done, why, check — or leaves one
  empty or out of order.
- `.github/CODEOWNERS` names the owner, so every pull request requests their review.
- `.github/ISSUE_TEMPLATE/decision-request.yml` mirrors the seven sections.

### 9. The register as precedent memory
`docs/decisions/` is the decision register ADR-0008 describes for the product, applied to the
project. It is the source from which Taktus will later propose turning a recurring decision into a
rule (ADR-0015 §4). That is why reclassified questions are recorded too: the pattern "this was
raised and did not need to be" is a precedent as much as an answer is.

*Amended 2026-10-01 (DEC-0039).* **A question an earlier decision answers is not a question.**
The session applies the precedent and cites it, and raises nothing. **The balance is measured
continuously:** `make status` shows, for every answered request, whether the owner chose the
recommended option, and for every notice, whether a later decision overrode it. A rate of
accepted recommendations near 100 % means too much is asked; many overridden notices mean too
much is decided alone.

*Amended 2026-10-01 (DEC-0042, the audit).* **The rate is reviewed, not only shown.** After every
twenty `unlisted` notices a request carrying the override rate is raised to the owner; the gate
fails the register when the count is reached and the request — a record carrying
`**Override review:**` — is missing. **The rate counts only what was asked before it was
answered.** A record written after the owner had answered carries `**Written after the
answer:**` and is left out of the rate, because its recommendation was written knowing the
answer: the naive count showed 5 of 6 recommendations taken where the audit of 2026-10-01 found 1
of 6.

## Alternatives
- **A checklist in CLAUDE.md, no tooling.** #1 was written under CLAUDE.md §8 and still failed. A
  rule that nothing checks is a hope.
- **Only the issue, no file.** An issue is a channel and can be edited, closed or lost; the
  repository is the record. The file is also what a gate can check without network access.
- **Only the file, no issue.** The owner would have to watch the repository for new files. An
  issue notifies, can be assigned, and is answerable from a phone.
- **Every open question is blocking.** Safe on paper. In practice the owner receives a queue in
  which the one blocking item is indistinguishable from five that were not, which is how #1's
  genuinely blocking item was the one presented least prominently.
- **Marking blocking through a label or a status check instead of draft.** A label can be removed
  by mistake; a required status check needs branch protection configured outside the repository.
  Draft is refused by GitHub itself and visible in the pull request list.

## Consequences
- Every pull request states near its top whether it needs the owner and for what. A description
  with the decisions at the end no longer passes the template.
- Raising a decision costs more than before: a file, an issue, seven sections. That cost is the
  filter — a question that is not worth seven sections was not a decision.
- A blocking pull request cannot be merged by anyone, including the owner, until the file has left
  `open/`. The owner can still decide quickly: one sentence in the issue, and the session does the
  rest.
- The register starts with the four items of #1, backfilled in the new shape (DEC-0001 to
  DEC-0004), so that the standard has worked examples from day one.

## Where this promise ends

The gate checks shape: sections present, fields filled, a date, an index entry, a draft flag
that matches. For a pull request description it checks that the four sections of §7 are there,
filled and in order; it cannot check that they are readable without the diff. It cannot check that a request is decidable by a person who has read neither the
diff nor the session — that is a reviewer's judgement — and it cannot check that a question
tested against the anchor page was tested honestly. A notice's evidence, and a `gate-weakened`
notice's demonstration that a gate had no value, are checked for presence and for naming a
gate, not for truth. A notice's kind is checked against the entry it cites, not against what
the notice describes: a behaviour change filed under `restructuring` passes the gate and fails
the reviewer. The draft rule holds on GitHub; a repository hosted elsewhere needs its equivalent.

The reversed default holds where the vision gives a direction; whether it does is the session's
judgement, which the owner reviews through the notices and the rate of overrides, not before.
The derivability test checks that a request names the four places it checked, not that the
check was thorough. The acceptance rate counts an answer as the recommended option only where
the record says "Option X" and the recommendation is marked; an answer of the owner's own is
counted as such. A gate that would fail a description holding an owner action without a linked
NEED or DEC was considered and not built: measured against every pull request description to
2026-10-01, it found one of the owner actions written as notes and raised two false alarms
(DEC-0039).
