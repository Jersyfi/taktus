# 2026-11-07 — The load one machine carries

The first measurement of S-04 (ADR-0223): how many concurrent runs one instance carries, at
which latency. It answers the roadmap's condition *Measured load behaviour* for one machine,
with the numbers below.

## What ran

The compose installation of this checkout (`deploy/docker/compose.yml`), built from source,
under a compose project of its own: PostgreSQL 16, Taktus with every role in one process and
the default four runner places (`TAKTUS_RUNNER_CONCURRENCY`), and the scheduled backup beside
them. Inside the Taktus container:

```bash
taktusctl load measure --process <the probe> --identity idn_load --levels 1,10,25,50 --timeout 900
taktusctl load measure --process <the probe> --identity idn_load --levels 100 --timeout 900
```

**Hardware**, as the measurement states it: Linux 7.0.14 (the container engine's virtual
machine), aarch64, 14 processors, 7.7 GiB of memory, on a laptop with an Apple M4 Max. The
database and Taktus shared the machine.

## The numbers

The probe is three rule steps (`blueprints/self-operation/processes/S-04-load-probe.yaml`). A
run's latency is the time from its creation to its end, as the instance's own records hold it.

| Runs at once | Median | 95th percentile | Longest | Runs ended per second |
|---:|---:|---:|---:|---:|
| 1 | 0.81 s | 0.81 s | 0.81 s | 1.2 |
| 10 | 1.52 s | 1.70 s | 1.70 s | 5.8 |
| 25 | 1.79 s | 2.28 s | 2.35 s | 10.5 |
| 50 | 2.39 s | 3.49 s | 3.59 s | 13.3 |
| 100 | 4.37 s | 6.94 s | 7.40 s | 13.5 |

Every run of every level finished. From 50 runs at once on, the throughput stays at about 13
runs per second, and the latency grows with the queue: the four runner places are the bound,
not the database. A run that waits for a person, a worker or a model takes as long as those
take, on top of this.

## What it does not say

The probe measures what every run asks of an instance, not what a business's process asks of
its workers and models. The number is one machine's, at the default runner places; more places
or a second instance (ADR-0002) carry more, and are not measured here. A cluster is not
measured. Package E's short performance test of 2026-11-03 measured the HTTP surface, not runs:
150 requests per second at 20 and at 50 at once, p95 285 ms and 756 ms, on one container.

## Frictions

None new. The first attempt of the scheduled backup beside it found two, fixed in the same
change: the backup started before the instance had migrated, and a fresh instance had no
directory of objects for the backup to archive (ADR-0222).
