---
id: UC-9.1
title: The process controlling cockpit
component: value
epic: E9
serves: [P7, P8]
state: specified
version: 0.5.0
tests: []
adrs: {ADR-0006: 4ef70c98354b, ADR-0010: 6b161e3f6831, ADR-0026: ccc4bd1f5423, ADR-0029: 37c061ef032a}
supersedes: null
---

# UC-9.1 — The process controlling cockpit

## 1. What must be achieved

Running processes gets a controlling layer. Every process has its figures — cycle time, quality,
cost, degree of automation, rate of escalation — with targets against actuals, trends, and
simulations such as "what happens if we allow autonomy level 3?". With them the business can be
steered precisely, not by feel.

The figures agree with the activity log: there are never two truths. Targets can be set per process,
and a deviation from a target produces a proposal of what to do.

## 2. How it is verified

- Each of the five figures is computed from the ledger and the records it references (ADR-0006), and
  has one definition wherever it is shown (ADR-0029). A test recomputes them from the ledger alone and
  finds the same values.
- Cost is shown in Takt and in money as accounting records them (ADR-0010), never in a third unit.
- A target can be set for each figure of each process, by a person with the right to steer the
  process. A figure outside its target produces a proposal (UC-4.4) that names the figure, the target,
  the period and the runs behind it.
- A simulation names the records it starts from and every assumption it makes, and is marked as a
  simulation wherever it is shown. A simulation of a higher autonomy level is computed from the
  decisions people actually took at the current level — how many were approved unchanged, how many
  changed, how many refused. A simulation changes nothing: raising autonomy stays the act of the
  process's owner (UC-15.5, ADR-0026).
- No figure of the cockpit is broken down by named person (principle 14).
- Every figure of the cockpit is in the export (UC-5.7).

## 3. Where the boundary lies

**Not the value balance**, which weighs cost against benefit and is UC-9.3. **Not the bottleneck
analysis**, which is UC-9.5. **Not a forecast tool.** A simulation answers a question from recorded
behaviour; it does not predict the market or the organisation. **Not the view.** Who sees the cockpit
is UC-6.4.

## 4. What it rests on

The ledger as the single source of every metric (ADR-0006); consumption in Takt and money (ADR-0010);
the autonomy statement and how a raise is proposed (ADR-0026); proposals (UC-4.4); the responsibility
anchor (UC-15.5); views and export (UC-6.4, UC-5.7). Filed in `value` with E9 (ADR-0029 files figures
with their owner). Definition `UC-9.1`. The roadmap's `0.5.0`.
