# DEC-0021 — Must a pull request Taktus opens update the status report?

**Category:** NON-BLOCKING
**Raised in:** [#26](https://github.com/Jersyfi/taktus/pull/26), which corrects the defect the first live run met
**Issue:** [#27](https://github.com/Jersyfi/taktus/issues/27)
**Needed by:** 2026-10-21
**Provisional answer:** Option A. P-03's task carries one more acceptance criterion — the repository's own rules for a change are met — and the first live run was repeated with it. Marked in the bundle by the comment above that criterion, and here.

## 1. What this is about

This repository has a rule for every change: the file that says where the project stands,
`docs/status.md`, is touched by any change to the state of the project, and a gate
(`make gate-status`) fails a change that did not touch it. "A change to the state of the
project" is, in the gate, a change to a file under `src/`, `workers/`, `blueprints/`,
`contracts/`, `deploy/`, `migrations/`, `tools/`, `docs/adr/`, `docs/decisions/` or to
`docs/roadmap.md`.

The rule was written for pull requests a person or a session opens. On 2026-09-23 Taktus
opened one itself for the first time. Its change — issue #11, adding `git` to the tool
preflight — touches `tools/` and the `Makefile`, and the coding worker did not touch
`docs/status.md`, because nothing told it to. The gate would have refused the change.

So: does the rule apply to a pull request Taktus opens, and if it does, who writes the status
update?

## 2. Why you are being asked

Because the question fits no entry of `docs/decisions/anchors.taktus.md`, and the page says
what to do then: raise it as a non-blocking request, continue on a marked provisional answer,
and propose which mode it belongs in (*Neither list*).

It is not a documentation defect: the gate and the rule agree with each other, and both say
what they mean. It is not mode 2 either. Deciding it by weakening the gate would be entry
M2.3, which needs a demonstration that the gate has no value — and no such demonstration
exists; the gate catches exactly what it was built to catch. Deciding it by changing what the
process asks of the worker is closer to M2.4, a behaviour change inside an agreed scope, and
that is what has been done provisionally — but the question underneath is about what a
pull request *must contain*, which is a rule of this repository and not an implementation
detail. That belongs to you.

**Proposed mode: 3** — the session prepares, you decide — as a new entry beside M3.2,
"what every change must carry". The work continues meanwhile; nothing is thrown away either
way, because the difference is one acceptance criterion in one bundle.

## 3. What you must decide

Whether a pull request Taktus opens must carry a status update like any other, or whether the
rule is about changes that change the state and a change that changes none is exempt — and, if
the first, who writes it.

## 4. What you need to know to decide

- **What the status file is.** Five sections: where the project is against the roadmap, the
  next pull requests, what is needed from you, what is blocked, promises not yet kept
  (ADR-0028 §3). Four of them are judgements. The fifth is generated from the register.
- **What the gate can and cannot see.** It sees that the file was touched, not that the touch
  was true; ADR-0028 says so in its own *Where this promise ends*. A rule that forces a touch
  where there is nothing to say produces exactly the untruthful touch the ADR warns about.
- **What the change in question actually changed.** `git` is now a tool the preflight knows
  about. The milestone did not move, no need was provided, nothing became blocked or unblocked,
  no promise was kept. There is honestly nothing for the status file to say — and the pull
  request in which Taktus first did such a thing is itself worth a line, which is the argument
  on the other side.
- **Who can write it.** In a P-03 run, only the coding worker edits files. It works from the
  issue, its acceptance criteria and the repository it cloned. It can read `CLAUDE.md` and
  follow it; it cannot judge whether the milestone moved.
- **What happens if nothing changes.** Every pull request Taktus opens is refused by its own
  pipeline, and P-03 never gets past `verify`. The completion criterion of `0.1.0` cannot be
  met. This is not a question that can stay open indefinitely, which is why a provisional
  answer is in force.

## 5. Options

### Option A — the rule holds, and the worker satisfies it (recommended)

P-03's task gains one acceptance criterion: the repository's own rules for a change are met —
whatever its contribution documentation requires of every change. The worker reads those rules
in the clone and follows them, as it follows the rest of the brief. For this repository that
means it touches `docs/status.md`.

For: one rule for every change, whoever makes it, which is the point of having the rule; the
pull request a reviewer opens looks like every other; the criterion is generic and names no
product, so it travels to a repository with different rules.
Against: the worker writes into a file whose four hand-written sections are judgements, and
it is not the one holding those judgements. The risk is a true-but-empty line, or a wrong one
that a reviewer has to correct. Mitigated by the fact that a person reads the pull request
before it merges, which is the same guard the criteria themselves have.

### Option B — the rule is about state, and a change that changes none is exempt

The gate learns a way to say "this change changed no state": a line in the pull request, a
marker in the commit, or a narrower directory list that separates the tools that *are* the
project's state from the ones that only help.

For: no untruthful touch, ever; the file stays a file people believe.
Against: it is a hole with a lid on it. Whoever writes the marker decides that nothing
changed, and the gate can no longer tell them they are wrong — which is a gate weakened by
another name, and M2.3 would want a demonstration nobody has. It also needs real work in the
gate, which this repository has so far kept blunt on purpose.

## 6. What is blocked

Nothing, while the provisional answer is in force: Option A is implemented in P-03's bundle
and the first live run was repeated with it. If you choose Option B, one acceptance criterion
comes back out and the gate gains a way to be told; no work is thrown away either way.

## 7. How to answer

"Option A" or "Option B" in issue [#27](https://github.com/Jersyfi/taktus/issues/27), with a
sentence on why. Option A also ends the question of who writes the update: the worker, under
the criterion, and the reviewer corrects it. Your answer extends
`docs/decisions/anchors.taktus.md` with the entry this request proposes.
