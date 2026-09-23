# DEC-0025 — The pull request Taktus opens could not pass the description checks

**Category:** DEFECT
**Raised in:** [#26](https://github.com/Jersyfi/taktus/pull/26), which corrects the defects the first live run met
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

This repository asks a shape of every pull request description, and two of its checks enforce
it. One reads the section `## Decisions required` and fails a description without it
(ADR-0017 §7). The other reads the last section, `## Needed from the owner`, and fails a
description whose last section is not the block that `docs/status.md` generates, so that the
owner sees what is needed without opening a file (ADR-0028 §3).

P-03 Implementation composed its pull request body from a template that had neither:

```
Closes #<issue>.

<the worker's summary>

---
Opened by Taktus, process P-03 Implementation: ...
```

On 2026-09-23 the first pull request Taktus ever opened, [#32](https://github.com/Jersyfi/taktus/pull/32),
was refused by its own pipeline for exactly that: *no `## Decisions required` section (see the
template)*. Everything else was green — the branch had already passed every gate, which is the
verdict P-03 reads before it opens anything.

Nobody had seen it because the two checks run on the `pull_request` event and not on a push,
and no process had ever opened a pull request. The branch passed; the pull request did not.

## 2. Why you are being asked

You are not. The repository requires a shape of a pull request and ships a process that opens
pull requests without it — the repository contradicting itself, in two files that had never
been read side by side. Entry M1.4 of `docs/decisions/anchors.taktus.md` makes the correction
the session's. The two checks are untouched; the process now meets them.

Whether the rules of *this* repository should apply to a pull request *Taktus* opens is the
open question DEC-0021, and this is the same question one step further out: DEC-0021 asks it
about the file every change must touch, this asks it about the description. The provisional
answer is the same and is in force — the rules hold, and the run satisfies them. An answer of
Option B to DEC-0021 takes both criteria out again.

## 3. What you must decide

Nothing here. DEC-0021 is where the question is.

## 4. What you need to know to decide

- **The run cannot compute the block.** `## Needed from the owner` must carry the generated
  block of `docs/status.md`, which is derived from the open records of the register. A
  template step has no way to read a file of the repository — there is no connector operation
  that reads one — so the run cannot put it there.
- **Who can.** The coding worker. It has the whole repository in its workspace, including
  `docs/status.md` and the pull request template, and it ends its assignment with a summary.
  So the summary is where the description comes from, and the bundle asks for it in the shape
  the repository prescribes rather than naming this repository's sections, which a blueprint
  must not know.
- **Why Taktus's own line moved to the top.** The check reads the *last* section of the
  description. A footer after it would be read as part of that section and the comparison
  would fail. What Taktus says about itself now stands under the `Closes` line, where a reader
  meets it first anyway.
- **What this makes probabilistic.** The description is now written by a language model within
  a `tolerant` step, and a summary that misses a required section fails the pull request's
  pipeline. That is visible, cheap and reviewed by a person; nothing merges on it. It is the
  same trade the bundle already makes for the change itself.

## 5. Options

None for the owner. What the session did, in two halves, split by method selection (ADR-0004)
rather than by convenience:

- **What is deterministic is a rule.** The body template writes `Closes #N`, Taktus's own
  statement of how the change was made, and the section that says which decisions the change
  requires — the one word `None`, which is not a judgement: a run has no way to raise a
  decision request, so the answer is the same every time, and the word is the one the check
  reads, alone: the section that follows it opens the summary, so that nothing the worker
  writes can fall into the section that must contain one word. Why it is `None` is said in the
  statement above it, where a reader is, and not in the section, where only the checker is. A fixed answer produced by a language model is the
  wrong method for it, and the first attempt showed why: the model wrote a fine description
  and left that section out.
- **What is a judgement is the worker's.** The summary is the rest of the body: what the
  change delivers and what a reviewer must know. The task's acceptance asks for it in the
  shape the repository prescribes — the same headings at the same level, the section the
  repository puts last, last, and a section whose content the repository *generates* copied
  rather than written afresh.

Both halves are generic: no section name of this repository is in the blueprint. The names
come from the repository, which the worker has in front of it.

**What is not done, and is [issue #34](https://github.com/Jersyfi/taktus/issues/34):** the section the repository generates — the one that
tells the owner what is needed — is a copy of a block that is in the repository, and a copy is
deterministic. The run cannot make it, because no connector operation reads a file, so it is
asked of the model instead. That is the wrong method for a copy and it is in the bundle
knowingly, with the reason and the fix in the issue.

Beyond that, nothing makes the summary right. A missing section is caught by the
pull request's own pipeline and a person, not by the run, because the run opens the pull
request before that pipeline exists. A run cannot check its own description.

## 6. What is blocked

Nothing. The run was repeated with the correction.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0025" in an issue, with the reading you hold.

## Outcome

**Corrected:** 2026-09-23
**What was wrong:** P-03's `pull-request-body` template produced a description with none of the
sections this repository's checks require, and put Taktus's own footer after everything, where
the last-section check would have read it. The first pull request Taktus opened, #32, was
refused by its own pipeline: no `## Decisions required` section.
**Why it was wrong:** a process that exists to open pull requests must open one the repository
accepts. The branch's verdict, which P-03 reads, says nothing about the description, so the
process could not have found out for itself.
**What it now says:** the body is `Closes #N`, Taktus's own statement of how the change was
made, the section naming the decisions the change requires — `None`, from the template,
because a run raises none — and then the worker's summary, with nothing after it. The
assignment's acceptance asks that the summary be the rest of the description, in the shape the
repository prescribes, with the section the repository puts last, last, and a generated
section copied rather than rewritten. The blueprint names no section of this repository.
**What changed in substance:** the shape of the description P-03 writes, and one more thing
asked of the coding worker. The change itself, the branch, the verdict and the label are
untouched.
**Recorded in:** [#26](https://github.com/Jersyfi/taktus/pull/26)
