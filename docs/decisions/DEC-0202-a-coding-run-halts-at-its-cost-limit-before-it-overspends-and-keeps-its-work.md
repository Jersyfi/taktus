# DEC-0202 — A coding run halts at its cost limit before it overspends, and keeps its work

**Category:** NON-BLOCKING
**Mode entry:** M3.10 (a limit)
**Raised in:** the session that took up the milestones `0.1.0` to `0.3.0`, on 2026-10-14; recorded in the pull request of its own that records the answer
**Issue:** none; the owner answered in conversation
**Needed by:** 2026-10-15
**Written after the answer:** the owner answered in conversation on 2026-10-15; left out of the acceptance rate (DEC-0042).

## 1. What this is about

On 2026-10-14 the instance's P-03 run for #277 used 17.4 million input tokens in 14 minutes,
about USD 10, although P-03's limit is USD 5 per run. The coding worker reports money only when
its assignment ends, and P-03 sets no token limit the worker could halt at on the way. The
coding agent's API workspace then reached its monthly usage limit, and every coding run failed.
In 30 hours P-03 used about 44 million input tokens, about USD 26, of which USD 4.83 was reported.

## 2. Why you are being asked

A limit is the owner's (M3.10); the provider account's limit is the owner's act.

**Sources checked:** ADR-0005 (a budget is a budget; the worker halts at its next boundary
before a running total crosses its ceiling, W-14), DEC-0193 (150 turns), DEC-0197 and DEC-0200.
None sets a limit the coding worker can halt at before money is reported.

## 3. What you must decide

Whether P-03's coding step gets a limit it halts at during the run, and the account's limit.

## 4. What you need to know to decide

Successful coding steps used 1.0 to 2.3 million input tokens; those that ended on a limit or
failed used up to 17.4 million.

## 5. Options

### Option A — a limit the worker halts at during the run (recommended)

- **Meaning:** a limit in a quantity the worker reports at every boundary, so that it halts at
  its next boundary before the run's money limit is crossed.

### Option B — no limit beyond the money reported at the end

## 6. What is blocked

P-03 on the instance, switched off on 2026-10-14 after the account's limit was reached.

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-10-15
**Answer:** Option A, with a condition. The owner raised the API workspace's monthly limit to
USD 50. On the limit, in the owner's words, translated: "I think it is fine, to make a cost
limit more measurable and to stop beforehand so that we do not overspend. But this must under
no circumstances lead to us putting money into runs needlessly, again and again, and the run
then breaking off in the middle. There are many causes, of course, but I think we simply have to
take care that we find an optimal or best possible middle way."
**Reasoning given:** the owner's: a limit must stop overspending without turning into money
spent again and again on runs that end half done.
**What it changes:**
- P-03's coding step gets a limit the worker halts at during the run, set from the measured use
  of successful steps with a margin.
- A run that reaches it halts at a boundary and keeps its work: it continues from its
  checkpoint when a person resumes it, never from the start, and nothing restarts it
  automatically.
- A run that ends on the agent's limit of turns is to keep its work the same way (#380).
- The daily watch reports every such halt, so that a person decides whether to resume, change
  the task or give it back.
- P-03 stays switched off on the instance until this is built.
**Recorded in:** this pull request
