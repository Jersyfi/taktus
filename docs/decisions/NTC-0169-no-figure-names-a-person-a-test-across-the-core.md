# NTC-0169 — No figure names a person: a test across the core

**Mode entry:** M2.2
**Kind:** test-strategy
**Decided:** 2026-10-11
**Raised in:** the pull request that closes issue #94

## 1. What was decided

Principle 14 is held by one architecture test across every component, instead of one test per
read. `tests/architecture/test_no_figure_names_a_person.py` reads every value type of the core —
the components, the ports, the shared kernel, `wire` — and every table of the database. It
fails when a **figure** names a person.

- A *figure* is a quantity: a field holding a number or a duration, directly or in a value the
  type contains.
- A field *names a person* when its name says it holds an identity: `actor`, `identity`,
  `reader`, `owner`, `author` and a few more, a name ending in `_by`, or a name containing
  `person` or `people`. `decider` is not one: it names a role (ADR-0042).

A type that names a person beside a figure passes in two shapes only, each listed in the test
with its reason:

- **one act**: a record of one act or a command for one, naming who acts as the audit requires,
  with that act's own quantities. A field named for a total over several acts — a count, a sum,
  a median, a share, a rate, a rank, a score — fails in it. A listed act inside another type is
  held on its own, so a run holding its step runs is not a figure of the person who confirmed
  one;
- **one's own**: a read computed for its reader, whose only person field is `reader`, beside the
  test that proves nobody else reads it under that name. Today that is the decision response
  times.

A field that groups by person, such as `by_person`, fails anywhere. A listed type or table that
no longer exists, or no longer names a person, fails, so the listing says what is. The rule is
shown to bite on values made for the purpose: a person beside a number, in a contained value,
and in a mapping by person.

What it found on its first run: nothing that breaks the rule. Every type that names a person
beside a quantity is a record of one act: a run and its step runs, the commands that act on
them, a ledger entry, a process version, a trigger's firing, a conformance run, a report's
history, a connector call. They are listed.

## 2. The evidence

- UC-13.5 §2: "The data model has no field that attributes a figure of work or performance to a
  named person outside that person's own view. A test fails when one is added." UC-6.4 §2 and
  ADR-0015's protective rule name the two exceptions: one's own response times and one's own
  view.
- ADR-0043 §7 and ADR-0006: who acted is the audit's, recorded in the ledger entry of the act.
- The test runs in `make gate-arch` in about a second; `tests/README.md` says the same.

## 3. What was considered

- **A marker on every type that is a figure.** Rejected: a figure added without the marker would
  pass. The test finds figures by their type instead, and a person by the field's name.
- **Recognise a person by a type of its own, not by a field's name.** Rejected for now: the
  identifiers are plain strings throughout the shared kernel, which is bound to the contracts'
  schemas (ADR-0019), and a new type there would change the binding of every contract that
  carries an identity. The limit is stated in the test: an identity kept under an unrelated name
  is not seen.
- **Keep one test per read, as before.** Kept, not replaced: the tests that prove a person's own
  read stay where they are, and the listing names them. They hold behaviour; the new test holds
  the shape of every type, including the ones nobody wrote a test for.

## 4. Which entry permits it

M2.2 of `docs/decisions/anchors.taktus.md`: "A change of test strategy and what the tests now
cover." No gate is weakened: a test is added to `make gate-arch`.
