# ADR-0282 — A limit is set per unit of the structure, inherited along it, and watched for harm

**Status:** accepted · extends ADR-0005 (a budget is held by admission), ADR-0166 (a unit's
monthly quota) and ADR-0260 (a tenant's monthly budget) · serves UC-8.5, UC-8.10

## Context

UC-8.5 asks for budgets per unit of the organisation's structure — the company, a department, a
team, a person — and per period or process. They inherit along the structure: a child's budget
never lets a step through that its parent's would refuse. An alert warns at a share of the
budget or of its forecast. At the line a policy applies. A forecast is a band, and an anomaly is
found by a rule or a statistic. UC-8.10 asks for the same per unit for every kind of limit, for a
view of what applies to a run or a process, and for a report when a limit itself does harm.

Three pieces exist. ADR-0005 holds each run to its own budget, step by step. ADR-0166 holds the
runs of one department to a monthly quota, committed when a run starts. ADR-0260 holds every run
of the tenant once its month is spent. None of them knows a team or a person, a week or a day, a
process, a share that warns, a forecast or a limit that does harm.

A run knows only the department it runs for (`Run.org_unit`). The structure below it — the team,
the project team — is where the commissioning identity sits in the directory.

## Decision

### 1. A unit limit

A tenant sets a **unit limit**: a named line for one unit of its structure.

- **Its name** is lowercase letters, digits and underscores. The ledger names it by that name.
- **Its unit** is a path below the tenant, `sales/field`. The empty path is the company.
- **Each person** of the unit may be held to the amount on their own, by the runs they
  commissioned (DEC-0069). The limit names no person. A limit naming one person beside an amount
  is a figure under a person's name, which principle 14 makes unbuildable in the data model
  (`tests/architecture/test_no_figure_names_a_person.py`). A budget for one person is a limit
  held per person on a unit, which may be a team of one. What one person spent against it is
  shown only to that person (§6).
- **A process** may be named. The limit then holds only that process's runs. A project is held
  as the unit of its project team, since a run names no project of its own.
- **Its period** is a day, an ISO week or a calendar month, in UTC.
- **Its amounts** are money per currency, compute seconds, or tokens; one or more of them.
- **Its policy at the line** is `halt` (the default) or `wait`. `halt` refuses the step and the
  run halts with cause `limit` for a person. `wait` parks the run until the limit's next check
  or the next period, whichever comes first.
- **Its alert shares**: shares of the amount at which the role is warned, `0.8` by default.
- **Its role**: who owns the limit and is told. A role, never a person.
- **Its rule for children**: `within` or `over`. With `within`, the limits set below it, for the
  same period and kind, may not together book more than it allows; a child that would is
  refused when it is set. With `over` they may. Booking under the parent is always allowed.
  Neither rule lets a step through the parent: §2 checks every limit on the path.

`taktusctl units limit set|clear|show` keeps them. `unit_limit.configured` records who acted.

### 2. Held by admission, along the path

A run is attributed when it is created. It records its path, `Run.org_path`: where its
commissioning identity sits in the directory, below the tenant, at that moment. A run whose
identity sits outside the department the command named is attributed to that department alone.

Every limit applies to a run whose path starts with the limit's unit, and whose process is
the limit's process where it names one. A limit held per person counts only the runs of the
identity whose run is admitted. Before a step is admitted, after it fits the run's own budget (ADR-0005), its reservation
is priced as admission prices it. It must fit what remains of **every** limit that applies.
What remains is the amount less what the matching runs of the period cost. That cost is their
recorded consumption, priced at the instance's table, with every step in flight counted at its
reservation, as `Run.consumed` counts it. A step that does not fit one of them is refused.
It is a rule over stored records, never a model. A rehearsal is never held.

A refusal opens the block `at_unit_limit` on the step, booked to `limit.budget`, naming the
limit. `unit_limit.held` names the limit by its outcome. Its digest holds the demand, the
period's cost and the amounts. When the step is admitted again the block ends, and
`unit_limit.released` records how long it was held. Where several limits refuse, `halt` wins over
`wait`.

### 3. Alerts, forecasts and anomalies

At every admission against a limit, the engine hands the governance component the period's
cost and the cost per day: for the period, and for the 28 days before it. A limit held per
person raises no alert, anomaly or line reached to a role (§6). For every other limit the
governance component decides, each by a rule or a statistic, never a model:

- **An alert** when the period's cost reaches an alert share of an amount. An alert also fires
  when the forecast's upper edge reaches the share. It is the incident `limit.alert`, addressed
  to the limit's role, once per period, share and basis.
- **A forecast** is a band. The days of the period so far give a mean daily cost and its
  standard deviation. Each edge projects the rest of the period at the mean less and plus one
  deviation, never below the cost already reached. The band names what it was computed from:
  the days, their first and last date, and that planned runs are not counted. It also says
  between which dates the amount is reached, or that it is not within the period.
- **An anomaly** is a day whose cost lies more than 3.5 robust deviations above the median of
  the 28 days before it. The robust deviation is the median absolute deviation times 1.4826.
  At least 7 days with a cost are needed, and a day that cost nothing is never one. It is the
  incident `cost.anomaly`, once per day.
- **The line reached** is the incident `limit.reached`, once per period.

### 4. A limit that does harm

A tenant configures a **limit watch**: a number of runs held, a number of seconds held, and a
window in days. Nothing is shipped; a tenant that configured none is told nothing. At every
refusal the rule reads the entries `unit_limit.held` and `unit_limit.released` of the window from
the ledger. The held time of a limit is the sum of its released durations. A hold still open
counts until now. Where the runs held or the seconds held reach the watch's figure, the
incident `limit.harmful` is raised to the limit's role, once per limit per period. It names:

- the limit and the work it held: runs, processes and seconds;
- the change recommended, to an amount that would have admitted the step it holds now, for the
  period's cost so far plus each held run's current demand;
- its cost: the amount the change adds per period;
- its benefit: the runs and the seconds the window held.

Taktus never changes the limit. Changing one is a person's decision (M3.10).

### 5. What applies to a run or a process

`taktusctl units applies <run>` shows what the run needs, what it used, and every limit that
applies, each with its unit. What it needs is its own budget and every step's reservation. What
it used is its consumption so far. The limits are its own budget, every unit limit on its path
with the period's cost and what remains, the department's quota (ADR-0166) and the tenant's
monthly budget (ADR-0260). `taktusctl units applies --process <id>` shows the same for a
process. Its need is what its runs of the current month cost, on average and at most.

### 6. A person's consumption is that person's

`taktusctl units consumption --viewer <who>` shows every limit with the period's cost, its
forecast and the alerts it reached. Against a limit held per person the viewer sees what their
own runs cost, and nobody else's; without a viewer, nobody's. `units applies` shows a run's
cost against such a limit only to the identity the run acts for. No view orders units or people
by what they consumed: limits come by unit and name. A harm report on a limit held per person
counts every person's holds together and names no one (principle 14, DEC-0069).

## Alternatives

- **Extend the department quota of ADR-0166 down the structure.** It commits a run's own budget
  once, when the run starts. A run without a money budget commits nothing, and a team below the
  department would need a commitment of its own for every level.
- **Hold at "reached", as ADR-0260 does.** It is cheaper: no reservation is priced. It lets every
  step that starts before the line through, however large. UC-8.5 asks that a step whose estimate
  does not fit is not admitted.
- **A model that forecasts or finds anomalies.** ADR-0023 forbids a model to decide an anomaly.
  A band from the days' mean and deviation, and a robust median rule, are reproducible.
- **Report on harm from a store of its own.** The ledger already carries every hold and how long
  it lasted; a second record could disagree with it.

## Consequences

- `governance/domain/model/unit_limits.py`: `UnitLimit`, `LimitWatch`, `forecast`, `anomalous`,
  `harm`. `governance/application/service/unit_limits.py`: `UnitLimits`. New incident kinds
  `limit.alert`, `limit.reached`, `cost.anomaly`, `limit.harmful`.
- `run/ports/unit_limits.py`: the run's port `UnitLimitsPort`. `Run.org_path`. The block cause
  `at_unit_limit`, with `OpenBlock.limit`. The engine's `_unit_refusal`, and its views
  `what_applies` and `unit_costs`. The ledger kinds
  `unit_limit.held` and `unit_limit.released`.
- `composition/unit_limits.py`: `UnitLimitsOfTheRun`, `applies`.
- `taktusctl units limit`, `units watch`, `units applies`, `units consumption`.
- Migration 0108: `unit_limit`, `limit_watch`, the column `run.org_path`.
- `tests/components/run/test_unit_limits.py`, `tests/components/governance/test_unit_limits.py`.

## Where this promise ends

- **Concurrent runners.** Two runners that admit a step against the same limit at the same
  instant both read the same cost. Both may fit, so a limit may be crossed by one step per
  runner admitting at once. Each crossing is recorded on its step, as ADR-0005's overrun is.
- **What is priced.** Money is known only at the instance's price table. A demand without a price
  is held only in the kinds it names: compute seconds and tokens. Money a worker reports when its
  assignment ends counts once it is reported (ADR-0005, first amendment).
- **The cheaper model.** The policy "continue on a cheaper model the process allows" is not
  built. A refused step is held by `halt` or `wait`, never moved to another model.
- **Attribution.** A run's path is where its identity sat when the run was created. A person who
  moves later does not take earlier runs along. A run whose identity is unknown to the directory
  is attributed to its department alone. A run's whole cost counts in the period and on the day
  it was created, also where it runs into the next.
- **Forecast.** The band is computed from the costs so far. It does not count the runs planned
  or expected, and it is no promise about them.
- **Anomaly and alerts.** Only a unit that holds a limit is watched. A watch is evaluated when a
  step of a matching run is admitted. A unit whose runs do nothing raises nothing.
- **Harm.** The rule runs at a refusal. A limit that holds no further step is not reviewed
  again. The recommendation names an amount from the demands the rule saw. It is no forecast of
  what a raised limit will cost.
- **Cost of a read.** Every admission reads every run of the tenant from the last 28 days and the
  period, as ADR-0260 does at every boundary.
- **Estimated demand before a run starts.** UC-8.10 asks that a run's estimated demand is shown to
  the person who commissions it before a run that needs much starts. This ADR does not build it.
  `units applies` shows it for a run that exists.
- **Limits not on consumption.** Concurrent runs stay a department's quota (ADR-0166). The
  platform's capacity stays ADR-0031's. Both are shown by §5 and not inherited.
