# DEC-0016 — The first run's variables are not in `.env.example`

**Category:** DEFECT
**Raised in:** [#22](https://github.com/Jersyfi/taktus/pull/22), which adds the needs request and the status report
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

The command that runs the first end-to-end, `tools/first_run.sh`, reads its settings from a
file named `.env` in the checkout and says in its own header that the names of those settings
are listed in `.env.example`, the template every operator copies. Three of the names were not
listed there: the three variables that point at the files holding the repository token and the
coding agent's credential (`REPOSITORY_TOKEN_FILE`, `CODING_AGENT_API_KEY_FILE`,
`CODING_AGENT_SESSION_FILE`). An owner following the steps of the needs requests raised in the
same pull request would have opened the template and not found the lines the steps tell him
to add.

Found on the way: the repository's front page counted "25 architecture decisions" while the
index listed 27, and 28 with the one this pull request adds.

## 2. Why you are being asked

You are not. This is a documentation defect: the repository contradicted itself (`first_run.sh`
said the names are in `.env.example`; they were not) and was wrong in a number. Entry M1.4 of
`docs/decisions/anchors.taktus.md` makes fixing it the session's, recorded here.

## 3. What you must decide

Nothing. The correction is made; the record exists so that the precedent is findable.

## 4. What you need to know to decide

- `.env.example` lists every variable an instance reads, with its meaning; an operator copies
  it to `.env` and fills in what applies. `.env` is ignored by git.
- `tools/first_run.sh` reads `.env` first and then checks that the three file variables are
  set; the check names each variable it misses, so the run was never at risk of starting
  without them. What was missing was the place an operator looks *before* running.
- The count on the front page is a number that changes with every architecture decision; the
  index is the source, and the front page now points at it without a count.

## 5. Options

None for the owner. What the session did: added the three variables to `.env.example` with
their meaning, next to the model endpoint's variables they belong with; replaced the count on
the front page with a description that does not go stale.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object to the correction: "Reopen DEC-0016" in an issue, with the reading
you hold.

## Outcome

**Corrected:** 2026-09-21
**What was wrong:** `.env.example` did not list `REPOSITORY_TOKEN_FILE`,
`CODING_AGENT_API_KEY_FILE` and `CODING_AGENT_SESSION_FILE`, although `tools/first_run.sh` reads
them from `.env` and says their names are in `.env.example`; `README.md` said the index holds
25 architecture decisions when it held 27.
**Why it was wrong:** the template is where an operator finds the names before running
anything; a name that is only in a script's header is found after the script has refused to
run. A count written by hand goes stale with the next decision.
**What it now says:** `.env.example` carries the three variables under *The first run*, each
with what the file it points at holds and where the steps to create it are (NEED-0001,
NEED-0002); `README.md` describes the index as "every architecture decision with the
alternatives rejected", without a number.
**What changed in substance:** nothing the software does. The same script reads the same
variables; they are now listed where the script says they are.
**Recorded in:** [#22](https://github.com/Jersyfi/taktus/pull/22)
