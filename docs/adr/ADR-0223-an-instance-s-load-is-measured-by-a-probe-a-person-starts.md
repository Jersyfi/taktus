# ADR-0223 — An instance's load is measured by a probe a person starts

**Status:** accepted · S-04 of `blueprints/self-operation/` · roadmap `1.0.0`, "measured load
behaviour" · builds on ADR-0002 (the queue and its runners)

## Context

The roadmap's condition for `1.0.0`: a number — how many concurrent runs one instance carries at
which latency, measured by S-04 on stated hardware, so that someone can answer the question
instead of guessing. Package E measured the HTTP surface on one container: requests per second
and their latency. That says how fast the instance answers, not how many runs it carries.

A run's latency has two parts. One is what the instance does for every run: a plan
commissioned, a run created, a job claimed by a runner, each step's boundary with its checkpoint,
its ledger entries and its provenance record. The other is what the run's steps ask of workers,
connectors and models, which their own measures already report per step (ADR-0084).

## Decision

### 1. A probe of rules

S-04's bundle is a probe: three rule steps over constants, at level 3, with takeover
instructions like every bundle (ADR-0180). Its latency is the instance's part alone.

### 2. A command that loads the instance and reads the runs' own records

`taktusctl load measure --process <the probe> --levels 1,10,25,50` registers the probe in the tenant it is given and,
for each level, submits that many runs at once through the queue, as `taktusctl submit` does.
It waits until every run has ended and reads each run's latency from its own record, the time
between `created_at` and `updated_at` as the instance's clock wrote them. Per level it reports
the runs per end state, the median, the 95th percentile by nearest rank and the longest
latency, and the runs ended per second from the first creation to the last end. The report
states the machine: system, architecture, processors, memory. It is printed, and written as
JSON with `--out`.

### 3. A person starts it, on the instance's machine

The measurement is not scheduled. It loads the instance it measures, and on a schedule it would
slow the business's runs at a time no one chose. A person runs it on the instance's machine, so
that the hardware it states is the instance's, in a tenant of its own, whose ledger holds the
probe's runs. A measurement worth keeping goes into `docs/runs/`.

## Alternatives

- **A self-operation process on the loopback connector.** A step of a run would wait for many
  runs on the same runners and could take a runner place from the runs it measures; at one
  runner place it would never end.
- **Measuring the HTTP surface again.** It is measured; it answers another question.
- **A load-testing product.** It would measure requests from outside and know nothing of runs,
  boundaries or the queue.

## Consequences

- `blueprints/self-operation/processes/S-04-load-probe.yaml`, in the control plane's image too.
- `adapters/driving/cli/load_command.py`; `tests/integration/test_load_measurement.py` runs it
  against a daemon of the test's own.
- `docs/runs/2026-11-07-the-load-one-machine-carries.md` holds the first number.

## Where this promise ends

The number is the instance's part of a run's latency, not a business process's: a step on a
worker or a model adds its own time. It is the number of the machine and the settings it was
taken on — runner places, database, other load — and changes with them; the measurement states
the hardware but not every setting. Submitting and waiting run in the same command, so the
submissions of a level are made from one process and arrive over a few moments rather than at
one instant. A run that never ends fails the level after `--timeout`; nothing measures a cluster
or several instances together, though each instance can be measured on its own.
