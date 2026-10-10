# DEC-0063 — Where #99's check on the installed instance is shown

**Category:** NON-BLOCKING
**Raised in:** [#108](https://github.com/Jersyfi/taktus/pull/108), while implementing issue #99: its fourth check cannot be shown before the instance is installed
**Issue:** [#110](https://github.com/Jersyfi/taktus/issues/110)
**Needed by:** 2026-10-20

## 1. What this is about

Issue #99 asked that Taktus act on the repository service as an app of its own, not as the
owner. Its section "How it is verified" names four checks. Pull request #108 meets three of them
within the pull request:

1. a design record and the credential register describe the app's identifier and key;
2. the connector's tests, against a fake of the service, show a token minted from the key, used,
   replaced before it expires and never shown, and a refused installation failing with the
   reason;
3. the connector's conformance suite passes as the app; the live test against the real service
   runs as the app, with a token minted in each run. That run happens on `main` after the merge,
   once the owner has placed the app in the live environment (NEED-0016), as the coding agent's
   live test did (NEED-0012).

The fourth check is: **a pull request opened by P-03 on the installed instance shows the app, not
a person, as its author.** *P-03* is the process that turns an issue into a pull request. *The
installed instance* is Taktus running on its platform. It is not installed yet: installing it is
issue #66, which waits for the chart, the image build and the cluster adapter (#64, #65). So the
fourth check cannot be shown in this pull request, whatever is built in it.

What was attempted: the live test now asserts, when it runs as the app, that the pull request it
opens on the scratch repository shows the app as an automation, not a person. That is the same
connector, the same app and the same service, but not P-03 and not the instance.

## 2. Why you are being asked

The definition of done says a requirement is met, or its failure is argued in a decision request;
it is never adjusted to become meetable (CLAUDE.md §11, point 13). Closing #99 with one check
unshown, or keeping it open for a check another task makes possible, are both choices about what
counts as done. No entry of the anchor pages covers that.

**Sources checked:** the vision (principle 12, production-ready: a check is shown, not
assumed) points to keeping the check binding but not to where it lives; ADR-0017 and ADR-0028
cover how a request and a need are raised, not when a task closes; `anchors.taktus.md` — M1.2
(ordering inside a scope) does not move a check between tasks, M3.15 (what a requirement
requires) is about use cases, and #99 is a task, not a use case; `docs/process/README.md` defines
"How it is verified" as the condition that must hold, not when; the register's precedent
NEED-0012 §6 lets a session run a live test after the merge, which covers the third check and not
the fourth, because the fourth needs another task's result.

## 3. What you must decide

Does #99 close with pull request #108, its fourth check carried to the task that installs the
instance, or does #99 stay open until that check is shown?

## 4. What you need to know to decide

- **Closing an issue** removes it from the backlog. A check that is not carried somewhere is then
  forgotten.
- **Issue #66** installs the instance on its platform, with its webhook intake. Its first P-03
  run there is where the fourth check can first be seen.
- **Carrying the check** means adding it to #66's verification, so that #66 cannot close without
  it.
- The fourth check fails only if the instance is configured with the personal token instead of
  the app. The connector and its tests are the same either way.

## 5. Options

### Option A — #99 closes; the check moves to #66 (recommended)

- **Meaning:** pull request #108 closes #99. #66 gains the check "a pull request opened by P-03
  on the installed instance shows the app, not a person, as its author".
- **Consequence:** the backlog shows #99 as done, and the check is held by the task that can
  make it true. Future tasks whose check needs another task's result are handled the same way,
  as a mode-2 notice (a proposed entry).
- **Effort:** one comment on #66 now (done provisionally), one line in its verification.
- **Reversibility:** cheap: reopening #99 is one click.
- **Why recommended:** the check stays binding and lands where it can be shown; an issue kept
  open only to wait for another is ceremony without substance.

### Option B — #99 stays open until the check is shown

- **Meaning:** pull request #108 refers to #99 instead of closing it. #99 is closed by hand after
  P-03's first pull request on the installed instance.
- **Consequence:** #99 sits in the backlog as ready while there is nothing to build; `make
  backlog NEXT=1` would offer it to the next session, which would have to skip it.
- **Effort:** a manual close later, and a mark on #99 so that sessions skip it.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing. The provisional answer is Option A: #108 says "Closes #99", and #66 carries the check in
a comment. If the answer is Option B, #99 is reopened and the comment on #66 is withdrawn.

## 7. How to answer

"DEC-0063: Option A." or "DEC-0063: Option B."

## Outcome

**Decided:** 2026-10-10
**Answer:** Option A. Pull request #108 closed #99; the check that a pull request P-03 opens on the installed instance shows the app, not a person, as its author belongs to #66, which cannot close without it.
**Reasoning given:** none beyond accepting the recommendation, whose reason was that the check stays binding and lands with the task that can make it true.
**Recorded in:** this pull request
