# NTC-0173 — A check's declared numbers are no person's figure

**Mode entry:** M2.3
**Kind:** gate-weakened
**Decided:** 2026-10-11
**Raised in:** [#228](https://github.com/Jersyfi/taktus/pull/228), for issue #91

## 1. What was decided

An architecture test holds principle 14 in the data model: no type may hold a number beside a
field that names a person (`tests/architecture/test_no_figure_names_a_person.py`, NTC-0169). It
reads every value type of the core, and every value contained in it.

A step can now declare checks (ADR-0082). A check carries numbers: the bounds a value must lie
within, the threshold above which a person confirms it, the share of results a person samples.
Those numbers are part of the process version, which names its author, and of the run, which
names whom it acts for. The test therefore read a plan, a run and a process version as holding
a figure under a person's name.

The test gains a third list beside its two, `DECLARED`: types whose numbers are parameters a
process declares, set by whoever writes it and never measured of anyone. The type around a listed
declaration is not read as holding its numbers. The declaration itself is refused the moment it
names a person. One type is listed: the shared kernel's `Check`.

## 2. The evidence

- `Check` has eleven fields: `kind`, `subject`, `total` (a text: which total), `source` (a
  capability), `reference`, `minimum`, `maximum`, `pattern`, `threshold`, `share`, `role`. None
  names a person; `role` is a role, refused unless it is a lowercase role name
  (`contracts/shared/v1/examples/check/invalid/approval-by-a-named-person.json`).
- Its numbers come from the bundle a person writes. Nothing in Taktus computes or updates them.
  They are constants of a process version, the way a budget's limit is.
- The five types the test refused — `Plan`, `CommissionPlan`, `ProcessVersion`, `StartRun`,
  `Run` — were refused only for `Check`'s numbers: before this change, the same test passed on
  each of them.
- The test keeps refusing the cases it was written for. A new test in the same file shows it:
  a type with a person and a number of its own beside a declaration is still refused, and a
  declaration that names a person is refused.

## 3. What was considered

- **List the five types under `ACTS`.** Rejected: `Plan` is not one act, and the three already
  listed would still be refused, because `share` and `total` are words of a total.
- **Rename the parameters, or carry them as text.** Rejected: a threshold is a number, and
  renaming to escape a word list hides the meaning from a reader while satisfying the test.
- **Exempt the whole step.** Rejected: too wide; a later field of a step that measured something
  would pass unseen.

## 4. Which entry permits it

M2.3 of `docs/decisions/anchors.taktus.md`: "Weakening or removing a gate, only where it is
demonstrated that the gate has no value." Adding an exception narrows what the gate looks at, so
it is this entry, and section 5 is the demonstration. No entry of mode 3 or 4 applies: principle
14 itself, a mode-4 matter, is unchanged.

## 5. Why the gate had no value

The gate is `tests/architecture/test_no_figure_names_a_person.py`, run by `make gate-arch`. For a
type that contains a `Check`, it looked at the check's `minimum`, `maximum`, `threshold` and
`share`, and at the names `total` and `share`. It would have caught a number that measures a
named person, or a total over several acts of one. A check's numbers are neither: they are
declared by the author of the process before any run, they describe what a result may be, and no
code writes them from what a person did. On those fields the gate could catch nothing but a
declared constant, in every case. Everywhere else it looks exactly as before: a listed
declaration that names a person fails, and so does a listed type that no longer declares a
number.
