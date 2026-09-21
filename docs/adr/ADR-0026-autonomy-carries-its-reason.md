# ADR-0026 — Autonomy carries its reason

**Status:** accepted

## Context
A process carried an autonomy level as a number: `autonomy: 3`. The number said at which
level the process runs and nothing else — not why, not what would have to be true for it to
run at the next one. Two things followed. A reader of a process could not tell whether level 3
was a considered choice or a default that nobody had revisited. And the direction the
governance model states — towards level 4, on evidence, never forced (governance.md §1) — had
no place to be written down per process, so that Taktus could not say, of any process, what it
would take to propose a raise.

The owner's answer of 2026-09-21: every process shows which autonomy level it is at, why, and
what is missing to go higher.

## Decision

### 1. The autonomy statement
Every process version carries an **autonomy statement** (`contracts/shared/v1/Autonomy.json`):

| Field | Meaning |
|---|---|
| `level` | the level the process runs at, 1 to 4 |
| `reason` | why it runs at that level: what the level rests on — the exactness of its results, the anchors it meets, the reversibility of its effects, the trust it has earned |
| `toward_next` | what is missing to go one level higher — a demonstrated quality history, a check that does not exist yet — or what forbids it where the process's requirements do not allow the next level. Required below level 4; absent at level 4, where there is no next level |

A bundle that names a bare level does not register; the finding says the shape it lacks. The
plan and the run carry the level alone, as before: they are commissioned from the version,
and the reason is the version's.

### 2. The direction, and that it is never forced
The direction is always towards level 4. It is never forced: a process whose requirements do
not allow it stays where it is, and `toward_next` says what forbids it — a legal anchor on
every step, a check that cannot be formulated. Where the conditions are met, Taktus proposes
the raise as a mode-3 decision with the evidence (`anchors.taktus.md` M3.9; the product's
mechanism from `0.2.0`). A raise is never applied by Taktus on its own; that is what M3.9 and
governance.md §1 say, and the statement is what makes the proposal writable: the evidence is
what `toward_next` asked for.

### 3. Shown wherever the process is shown
`taktusctl run` prints the statement under the run's header. Each blueprint's README states it
per process that runs. The web app (`0.3.0`) shows it on the process page and in the dashboard.
A place that shows a process without its autonomy statement is a documentation defect.

## Alternatives
- **The reason in the process's description text.** Free text nobody can query, and the
  direction — what is missing — would have no field, so no proposal could be derived from it.
- **A separate governance record per process.** A second place to keep current; the statement
  belongs where the level is, because the two are read together.
- **Derive the reason from the steps.** Which anchors a process meets and how exact its
  results are can be derived; why an owner trusts a process at level 3 cannot.

## Consequences
- `contracts/shared/v1/Autonomy.json` exists with examples; `ProcessVersion.autonomy` is the
  binding; the bundle's `autonomy` field is the statement; `process_version.autonomy` is a
  column beside `autonomy_level` (migration 0007, with a backfill that says the row predates
  the requirement).
- Every bundle of this repository carries a statement: the example, P-02, P-03, S-01. The
  blueprint descriptions carry one per process.
- Raising a level of a process of this repository is M3.9 in `anchors.taktus.md`.

## Where this promise ends
The statement is a declaration by whoever wrote the bundle; Taktus checks that it is present
and well-formed, not that it is true. Nothing in this version measures a quality history or
proposes a raise; the proposal is `0.2.0`, when governance exists, and until then a raise is a
person's edit of the bundle under M3.9. "Shown wherever the process is shown" holds for the
command line and the READMEs today; the web app does not exist yet. Rows registered before
this decision carry a backfilled statement that says so and is replaced at the next
registration.
