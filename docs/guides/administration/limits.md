This page sets what work may cost, where data may be processed, and how work is stopped. Every
command is a `taktusctl` command, run inside the instance as *Installing from nothing* shows in
its section 1. Each takes `--tenant <tenant>`, and `--identity` names who acts, for the ledger.

## A monthly budget for the tenant

The **budget** is what all runs of the tenant may cost in one month. Once the month's runs cost
it, every run waits before its next step. The role you name is told once.

```bash
taktusctl budget set --amount EUR=<amount> --role finance-lead --tenant <tenant>
taktusctl budget show --tenant <tenant>
```

A raised budget, or the next month, lets the waiting runs go on. What is left of the month is
also the ceiling of a worker step that is handed over: a worker that reports its money as it
goes halts there during the step and keeps its work (ADR-0335).

Money a worker or a provider reports in another currency than the budget's counts against it
only at an **exchange-rate table** the operator loads: a JSON file named by
`TAKTUS_EXCHANGE_RATES`, with a `version`, the moment `valid_from`, the `source` of the rates and
`rates` from each currency into others, such as `{"usd": {"eur": 0.9}}`. Without it, such money
counts against nothing.

## Limits per unit

A **limit** holds a unit of the structure (*Structure, people and rights*) to an amount of money,
compute seconds or tokens per day, week or month. It holds every process of the unit, or one.

```bash
taktusctl units limit set monthly --unit finance --budget 250eur --period month --role finance-lead --tenant <tenant>
```

- `--unit` is the unit's path below the tenant, such as `sales/field`; without it, the limit
  holds the whole company.
- `--per-person` holds each person of the unit to the amount on their own.
- `--policy halt` stops a run at the limit until a person resumes it; `--policy wait` lets it
  wait and try again every `--check-every` seconds, until it fits or the next period begins.
- `--alert-at 0.8` warns the role at 80 per cent of the amount; repeat it for several shares.
- `--children within` keeps the limits below this one inside it; `over` lets them go beyond.

A step starts only where its reserved cost fits every limit above it. Warnings, a limit reached,
and unusual consumption reach the limit's role as incidents. Taktus never changes a limit itself.

```bash
taktusctl units consumption --tenant <tenant>          # every limit: spent, forecast, warnings reached
taktusctl units applies <run> --tenant <tenant>        # what holds one run, and from which unit
taktusctl units watch --held-runs 20 --tenant <tenant> # when a limit counts as doing harm
taktusctl bottlenecks --tenant <tenant>                # what a higher limit would have bought
```

## Where data is processed

The **residency rule** says where the tenant's data may be processed: `own` (on the
organisation's own infrastructure), `eu`, or `anywhere`. It can be narrowed for a class of data
and for one process, never widened. For a run, the narrowest rule holds when a model or a worker
is chosen.

```bash
taktusctl residency set --location eu --class personal=own --process payroll=own --tenant <tenant>
taktusctl residency show --tenant <tenant>
```

The rule may also demand the provider's terms of a model the data is sent to: a
data-processing agreement in place, and no training on the data. The operator declares what each
model's provider agreed, with `TAKTUS_MODEL_TERMS` or `TAKTUS_MODELS_<MEMBER>_TERMS`; a model that
does not declare what the rule demands is never sent that data (ADR-0334).

```bash
taktusctl residency set --terms processing-agreement,no-training --tenant <tenant>
taktusctl residency set --class-terms customer=processing-agreement+no-training --tenant <tenant>
```

## Outward messages

The **message rules** hold every message a process sends: the label added to what a model wrote,
the delay after approval, the quiet hours, the **recipient limit** — the most recipients one
outward step addresses without a person, ten unless the tenant sets another — and the **daily
limit**: the most messages a process sends within 24 hours without a person, none unless set.
Beyond either, the step waits for a person's decision.

```bash
taktusctl messages set --recipient-limit 3 --tenant <tenant>
taktusctl messages set --daily-limit 20 --tenant <tenant>                    # every process
taktusctl messages set --daily-limit 5 --process <process> --tenant <tenant> # one process
taktusctl messages show --tenant <tenant>
```

A step that acts on behalf of a person reads with that person's credential and never sends or
writes: nothing leaves in a person's name (ADR-0332).

## Falling back by count

A process falls one level when its correction rate rises above the tenant's limit. A count may
lower it too: so many corrections within so many days, for the tenant or for one process. It
counts decisions, never who made them (ADR-0333).

```bash
taktusctl corrections configure --lower-count 3 --lower-count-days 14 --tenant <tenant>
taktusctl corrections configure --lower-count 3 --process <process> --tenant <tenant>
taktusctl corrections list --tenant <tenant>   # each window's rate and count of corrections
```

## Stopping work

A **stop** halts every run it covers before its next step. A running step is never broken off.
No stop asks for a reason.

```bash
taktusctl stop process payroll --tenant <tenant>   # every run of one process
taktusctl stop tenant --tenant <tenant>            # every run of the tenant
taktusctl stop global                              # every run of every tenant on this instance
taktusctl stop adapter <adapter> --tenant <tenant> # every step one worker, connector or model serves
taktusctl stop list --tenant <tenant>
```

Each command waits up to a minute (`--wait`) and prints the stop once every run it covers has
halted. A held stop raises an incident for the on-call role, `operator` unless
`taktusctl incident configure --on-call` names another. `taktusctl stop lift <stop>` ends a stop
of an adapter. The runs a stop halted stay halted until a person resumes them.

In the web app, the page *What acts* has a stop for each thing that acts for the organisation.
