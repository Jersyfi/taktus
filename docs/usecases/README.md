# Use cases

What Taktus must be able to do, as requirements. This layer answers **what**;
`docs/vision/` answers why, `docs/adr/` how it was decided, `docs/architecture/` how it is
built.

A use case is written before its version and is not implementation. The implementation arrives
in the version the use case names and is held to it by tests. Whether it holds is not claimed:
the state says it, and the gate checks the state.

---

## Two levels

**Blueprint-level cases** describe one whole business function run by Taktus: which processes,
at which autonomy, with which anchors. One file per blueprint, numbered `UC-<nn>`.

| Case | Blueprint | File | Version |
|---|---|---|---|
| UC-01 | product development, unattended | [AF-01-dev-orchestration.md](AF-01-dev-orchestration.md) | `0.4.0` |
| UC-02 | systems operation, unattended | [AF-02-it-operations.md](AF-02-it-operations.md) | `0.7.0` |

**Function-level cases** describe one thing Taktus does, for every blueprint, as a
requirement the implementation is held to. They are numbered `UC-<area>.<case>` and filed by
bounded context, in a folder named exactly as the component under `src/taktus/components/`:
someone working on `run` finds the requirements where they find the code. How numbers are
given, and where a number used elsewhere points here, is [NUMBERING.md](NUMBERING.md).

`make usecases` prints every function-level case with its component, state and version, and
`make gate-vision` prints which cases serve which principle. Neither list is stored here: a
stored list would be edited by every pull request that adds a case, and two of them would
conflict on it (CLAUDE.md §9).

### Moved from their first files

Seven cases were first written outside this format — UC-4.11, UC-4.12, UC-6.8 and UC-7.2 in
`UC-4-result-defects.md`, UC-4.13 and UC-6.9 in `UC-4-exactness-statement.md`, and UC-4.6 as a
state of `docs/architecture/control-plane.md` §5.2. The migration's second step moved them into
their components' folders, and the two first files were removed (`MIGRATION.md`, NTC-0029). The
earlier shape had five parts — the situation, what Taktus does, what it needs, what it never does,
and how it is proven. The format below keeps all five: the situation and what Taktus does became
section 1, what it never does and how it is proven became section 2, and what it needs became
section 4.

---

## The format

Every function-level case is one file, `<component>/UC-<area>.<case>-<slug>.md`, with front
matter and four sections. [TEMPLATE.md](TEMPLATE.md) is the file to copy.

```yaml
---
id: UC-4.10
title: Deviation detection
component: run
epic: E4                  # optional: the epic of the original definition
serves: [P8, P10, P12]    # which principles, P1 to P14 — at least one
state: specified          # specified | building | built | verified | retired
version: 0.5.0            # the milestone that implements it
tests: []                 # path::test_name — required once state is `built`
adrs: {ADR-0021: 3f09c2a1b7de}   # every ADR the file names, with the digest it was checked against
supersedes: null          # a use case this one replaces, or null
---
```

### 1. What must be achieved

The outcome, never the route. This is the part that belongs to the owner.

### 2. How it is verified

The condition that must hold. **This is the section that does the work.** A verifiable
condition cannot be softened by interpretation, and a vague one invites exactly that. What the
use case must never do is a condition too, and belongs here.

> "A result is checked against expected properties" — soft, unusable.
> "A distribution shift beyond threshold X produces a finding with a bounded window" — a
> condition.

### 3. Where the boundary lies

What is explicitly **not** required. Same shape as *Where this promise ends* on an ADR, and it
works in both directions: it stops too little being built, because what is required is clear,
and too much, because what is not required is clear as well.

### 4. What it rests on

What the use case needs from elsewhere — other use cases, ADRs, contracts, a milestone — and
where the definition's original text said it. This section describes; it requires nothing.

---

## States

| State | Meaning |
|---|---|
| `specified` | written and agreed; nothing built |
| `building` | in progress; the tests it names exist and cover part of section 2 |
| `built` | implemented; `tests` names at least one test |
| `verified` | the named tests pass: `make gate-usecases` runs them and fails when one does not |
| `retired` | no longer required; the file stays, with `supersedes` on its replacement, because the record of what was once wanted is part of the reasoning |

**The state is derived, not claimed.** `verified` is reached only when the tests the use case
names are green. The repository therefore answers honestly at any time how much of the vision
actually stands, and nobody has to take that on trust.

---

## Who may change what

| | Mode | Entry |
|---|---|---|
| What a use case **requires** — sections 1 to 3 | **3** — a session prepares, the owner decides | M3.15 |
| How it is **described** — wording, examples, links, section 4, the front matter's state, tests and digests | **1** — a session, no notice | M1.10 |

The entries are in `docs/decisions/anchors.taktus.md`.

### The rule that protects the requirement

**A use case is never changed in the same pull request that implements it.** Never.

Whoever finds while building that the requirement does not hold opens a decision request: the
precise point where it fails, the constellation of use cases involved if there is one, and a
worked proposal. The implementation waits.

This is a hard separation and it is the strongest protection available: as long as changing and
implementing cannot happen in one step, bending a requirement is no longer a shortcut. It is a
detour.

A use case's **implementation** is, for the gate, its component's code and tests
(`src/taktus/components/<component>/`, `tests/components/<component>/`) and the files of the
tests it names. A new use case counts as a changed one: writing a requirement in the change that
builds it is the same shortcut.

### The rule that protects the work

Failing a task is allowed and correct when it cannot be done. **Reporting instead of working is
not.**

The difference is checkable: a decision request that does not name what was attempted and where
exactly it failed is not a request but an evasion, and is returned as one.

In the definition of done: *a requirement is met, or its failure is argued. It is never adjusted
in order to become meetable.*

---

## Gates

`make gate-usecases` (`tools/check_usecases.py`) fails on:

- a use case without a state, without a verification condition, or serving no principle
- a use case in state `built` or `verified` naming no test, or naming a test that does not exist
- a use case in state `verified` whose named tests are not green
- an ADR that changed after a use case was checked against it — the ADR contradicts the use case
  without having touched it, or nobody looked
- a pull request that changes what a use case requires and touches its implementation

`make gate-vision` (`tools/check_vision.py`) fails on a principle that no use case serves —
either a missing requirement or an empty principle.

**How an ADR stays in step with a use case.** Every ADR a use case names is listed in its front
matter with a digest of the ADR's text, as it was when the use case was last checked against it.
When the ADR changes, the digest no longer matches and the gate fails, naming the ADR and the use
cases resting on it. The pull request that changed the ADR then does one of two things for each:
it re-reads the use case, finds that it still holds, and records the new digest (mode 1); or it
finds that the ADR now contradicts the use case, and raises a decision request (mode 3), because
the use case is the owner's. It is the same mechanism as *Where this promise ends*: the gate
cannot read, but it can make sure that somebody did.
