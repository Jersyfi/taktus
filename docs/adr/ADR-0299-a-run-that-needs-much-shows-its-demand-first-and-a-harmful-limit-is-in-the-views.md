# ADR-0299 — A run that needs much shows its demand first, and a harmful limit is in the views

**Status:** accepted · supersedes the bound *Estimated demand before a run starts* of ADR-0282 ·
extends ADR-0241, ADR-0282 §4 · serves UC-8.10

## Context

UC-8.10 asks two things that ADR-0282 left open.

- **The demand before the start.** Before a run that needs much starts, its estimated demand is
  shown to the person who commissions it. ADR-0282 shows what applies to a run that exists
  (`taktusctl units applies`), not before it exists.
- **The report in the views.** A limit at which work is held too often or too long produces a
  report to the limit's owner *and in the views of the administrator, management and the team
  affected*. ADR-0282 §4 raises the report as the incident `limit.harmful` to the limit's role.
  No view shows it.

A view shows figures. Each figure has an owner component, a scope and a subject, and a view
shows the figures whose scope is the unit it groups by (ADR-0241). A scope is never a person.

## Decision

### 1. A run's estimated demand, before it starts

`RunEngine.demand` gives a run's estimated demand before the run exists. It reads, by rule,
from the stored runs:

- **the estimate**: the mean cost of the process's finished runs of the last 28 days, per line —
  money per currency, compute seconds, tokens. Where the process has no such run, the estimate
  is what the run's budget allows at most. The basis is named either way.
- **the dearest** of those runs, and **what the budget allows at most**;
- **every unit limit on the run's path** (ADR-0282 §2), with what remains of it this period. A
  limit held per person counts only the commissioning person's own runs (ADR-0282 §6).

A run **needs much** where its estimate reaches a share of what remains of a limit, in any of
its lines. The share is an engine option, `demand_share`, 0.5 by default.

A start names whether a person commissions the run there (`StartRun.demand_accepted`):

- `None`: no person commissions it there — a trigger, a deadline, a reaction, a trial, a
  rehearsal. Nothing is shown. Those runs are commissioned by whoever configured the process
  (ADR-0237).
- `False`: a person commissions it and has not accepted its demand. A run that needs much is
  refused with `DemandToAccept`, which carries the demand. Nothing is written.
- `True`: the person saw the demand and accepted it.

`taktusctl run` and `taktusctl submit` ask for the demand before they commission anything. A
run that needs much prints its demand, writes nothing, and exits with code 4. `--accept-demand`
starts it.

### 2. A harmful limit is a figure of its unit and of each process it held

The rule of ADR-0282 §4 also records, in the report's facts, the seconds it held per process.

The composition reads the open `limit.harmful` incidents, the last per limit, and hands them to
`reporting` as the figure `limit.held_seconds`, owned by `governance`:

- once with the scope `unit` and the limit's unit as its subject: the view of the team
  affected, and of the administrator;
- once per visible process it held, with the scope `process`: the views grouped by process.

Its value is the seconds held in the watch's window. Its basis is the report: the limit, the
runs and processes held, the amount recommended, its cost per period, its benefit and the role
that owns the limit. It names no person. A limit held per person counts every person's holds
together (ADR-0282 §6).

The shipped default views (ADR-0241 §2) add the figure to `team` and `management`, and gain a
sixth example view, `administration`, grouped by unit. As every default view, they are held by
`owner` until the tenant configures its own. Which role holds which view stays the tenant's
configuration.

## Alternatives

- **Show the demand after the run was created, and hold its first step.** It would create a run
  and a commissioned plan for something the person may decline. A refusal before anything is
  written leaves nothing to clean up.
- **A threshold in money.** A fixed amount means nothing to a tenant whose limits are in tokens
  or seconds, and a different thing per currency. A share of what remains of the tenant's own
  limits is measured against the lines the tenant set.
- **Estimate from the plan's own estimates.** A plan of a process carries no estimate per step;
  only a drafted plan does (ADR-0237). The process's past runs exist for every process that ran.
- **A view of its own for limits, outside the figures.** ADR-0241 makes every view a selection
  of figures, so that what a view shows is also in the export. A figure keeps that promise.

## Consequences

- `run/application/service/execute_run.py`: `RunEngine.demand`, `StartRun.demand_accepted`,
  `EngineOptions.demand_share`. `run/domain/model/errors.py`: `DemandToAccept`.
- `adapters/driving/cli/run_command.py` and `submit_command.py`: `--accept-demand`, exit code 4.
- `governance/domain/model/unit_limits.py`: `Harm.by_process`; the report's facts
  `held_seconds.<process>`.
- `composition/figures.py`: the figure `limit.held_seconds`. `composition/reports.py` hands
  `FigureReads` the incidents. `reporting/domain/service/views.py`: the default views.
- `tests/components/run/test_run_demand.py`, `tests/adapters/rest/test_limit_figures.py`.

## Where this promise ends

- **Only where a person commissions here.** The demand is shown where a surface names the
  person who commissions the run — the command line's `run` and `submit` today. A start that
  names no person, and every surface that does not ask for the demand, starts as before.
- **Much is measured against unit limits.** The share is taken of what remains of the unit limits
  on the run's path. A run's own budget, the department's quota (ADR-0166) and the tenant's
  monthly budget (ADR-0260) are shown nowhere in this estimate, and a tenant without unit limits
  is shown nothing.
- **The estimate is the past.** It is the mean of the process's runs of 28 days, or its budget.
  It does not read the inputs of the run to come; a run with a larger case may cost more.
- **The view shows the last report.** A figure shows the last open `limit.harmful` report of a
  limit. A closed report is not shown, and the figure is not computed again between reports.
- **A view grouped by process sees the processes the reader sees.** A process the reader may not
  see adds no figure, and the unit's figure still counts its seconds.
