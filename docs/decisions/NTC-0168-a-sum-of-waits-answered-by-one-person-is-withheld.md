# NTC-0168 — A sum of waits answered by one person is withheld

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-11
**Raised in:** the pull request that closes issue #94

## 1. What was decided

A *wait on a person* is a stretch of time in which a step waited for a person to answer: to
confirm it, to perform its act, or to decide an anchored act. Taktus books it to the account
`wait.human` (ADR-0043). The read `sums` adds these waits up per process and per period, for
anyone to read.

From now on, a sum of `wait.human` that fewer than two distinct persons answered is withheld.
It keeps its account, its process, its period and the number of runs the process had, and says
why it is withheld. It carries no figure of the wait: no seconds, no count of blocks, no runs or
steps held up, no share. A sum that two or more persons answered is shown as before. The person
who answered still reads each of their own waits under their name (`own`).

The time other steps were held back behind such a wait, booked to `wait.dependency`, is the
process's and stays whole.

## 2. The evidence

- ADR-0042 and NTC-0088 decided that an aggregate of decision response times over fewer than two
  deciders is withheld, "count and all, because it is one person's number under another name".
  A sum of `wait.human` is an aggregate of response times too: each wait ends when a person
  answers. Summed over one person, it is that person's response time under the name of a
  process. The precedent applies (anchors.taktus.md, *the register as precedent*).
- Principle 14 forbids any metric that appraises a named person. UC-13.5 §2: "A group so small
  that it would identify one person is not shown."
- The owner's paragraph of 2026-10-10 asks for processes analysed per step, role and department,
  and says that nobody sees who is slower (DEC-0123). The `wait.dependency` sum and every other
  account stay whole, so the analysis keeps the time lost in a process.
- `tests/components/run/test_blocked_time.py::test_a_sum_of_waits_answered_by_one_person_is_withheld_count_and_all`:
  two waits answered by one person are withheld, a third answered by another shows all three.
  `test_a_sum_is_shown_with_every_figure_or_withheld_with_none`: a sum carries every figure or
  none.

## 3. What was considered

- **Leave the sums as ADR-0043 built them.** Rejected: the same number ADR-0042 withholds for
  response times would be readable here under the process's name.
- **Withhold the `wait.dependency` sum behind a person's wait as well.** Rejected: it is the
  process's lost time, which principle 14 asks to be analysed. A run's lead time contains a
  person's wait as well, and is not withheld either.
- **Withhold below a larger group, such as five.** Rejected: two is the threshold the register
  already holds for response times (NTC-0088). A different number for the same kind of figure
  would be two rules for one thing.

## 4. Which entry permits it

M2.4 of `docs/decisions/anchors.taktus.md`: "A change of what the software does, made inside an
agreed scope, that breaks no contract, moves no limit or autonomy level and says nothing public."
The scope is issue #94, in `0.5.0`: principle 14 enforced in the data model. The sums are read
inside the `run` component and published in no contract. No limit or level moves. ADR-0043 is
amended to say the same (M1.9).
