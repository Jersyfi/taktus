# NTC-NNNN — <title: what was decided, in five words>

**Mode entry:** <M2.N, the entry of anchors.taktus.md mode 2 that permits deciding this alone>
**Decided:** <YYYY-MM-DD>
**Raised in:** <link to the pull request>

<!--
Copy this file to docs/decisions/NTC-NNNN-<slug>.md, with the next free notice number.
Fill every section. Replace every <placeholder>; the gate fails on any that remains.
A notice is a mode-2 record (anchors.md §1): the session decided, nobody approves, and the
record says what was decided and on what evidence. It is not a note in a pull request — a
note disappears with the pull request; a notice stays in the register.
Section 5 exists only for M2.3, a weakened or removed gate, and is then mandatory: the gate
fails an M2.3 notice without it, and a notice of any other entry with it.
Mechanism: docs/adr/ADR-0017 §2a.
-->

## 1. What was decided

<The decision in plain sentences: what is different now. A reader who knows Taktus only from
the README must be able to follow.>

## 2. The evidence

<What the decision rests on: measurements, counts, the documents compared, the runs observed.
Facts a reader can check, with where to check them.>

## 3. What was considered

<The alternatives, each with why it was not taken. At least one.>

## 4. Which entry permits it

<The mode-2 entry of docs/decisions/anchors.taktus.md, quoted with its identifier, and one
sentence on why this decision falls under it and under no entry of mode 3 or 4.>

## 5. Why the gate had no value

<M2.3 only; delete this section otherwise. Name the gate — its make target or its test path.
State what it looked at, what it would have caught, and the evidence that it caught nothing
and could catch nothing: how many runs, over which period, what the same finding is caught by
instead. "It was in the way" or "it was slow" is not evidence; a slow gate is a finding to
report with its cost, not a gate to remove.>
