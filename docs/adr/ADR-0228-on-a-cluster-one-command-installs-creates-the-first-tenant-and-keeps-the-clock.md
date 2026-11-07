# ADR-0228 — On a cluster, one command installs, creates the first tenant and keeps the clock

**Status:** accepted · builds on ADR-0136 §6 and ADR-0104 · serves UC-10.4 · issue #405

## Context

UC-10.4 asks that one command installs Taktus, on one machine or on a cluster, and that the time
from that command to the end of a first rehearsal is recorded by a clock, never estimated.
ADR-0136 §6 built it on one machine: `make start` brings the containers up, runs
`taktusctl first start` and keeps a clock (`deploy/docker/start.py`). On a cluster the chart was
installed by `helm`, the first tenant had to be created by hand with `taktusctl tenant create`
in a pod, and no clock ran.

## Decision

1. **One command.** `make start-cluster` runs `deploy/k8s/start.py`. It installs or upgrades the
   chart with the operator's own values files (`helm upgrade --install`), against the cluster
   `kubectl` points at. With `--installed` it takes a release that stands already, and the clock
   starts then. It waits for every deployment of the namespace to roll out.
2. **The first tenant in a pod of the control plane.** It runs `taktusctl first start` in a
   running pod labelled `app.kubernetes.io/component=control-plane`, in its container
   `taktusd`. That is the command `make start` runs, so a cluster's first tenant and its
   administrator `idn_admin` are created the same way, once, and the key is printed once.
3. **The same clock.** The clock is `deploy/docker/start.py`'s `wait_for_rehearsal`, loaded by
   the cluster's script, so both installs measure the same way: every five seconds
   `taktusctl first rehearsal` in the same pod, until the tenant's first rehearsal finished. The
   record, `deploy/k8s/first-process.json`, holds the stages' times, the cluster's server
   version and node count, and whether the total was within ten minutes. It never holds the key
   and names no person.

## Alternatives

- **A chart hook that creates the tenant.** A hook runs without a person watching it, and the
  key would land in a job's log. The key is shown once, to the person who typed the command.
- **An administration key in the chart, and the tenant created over HTTP.** The chart mounts no
  administration key on purpose (ADR-0104); the command line in a pod is the administration on a
  cluster.
- **A second clock written for the cluster.** Two clocks would measure two ways. One function
  serves both.

## Consequences

- `deploy/k8s/start.py`, the target `start-cluster`, and `wait_for_rehearsal`, `machine` and `told`
  factored out of `deploy/docker/start.py`, which keeps its behaviour.
- `tests/deploy/test_start_cluster.py` runs the command against stand-ins for `helm` and `kubectl`.
- `deploy/k8s/first-process.json` is ignored by git.

## Where this promise ends

- Installing the release stays the operator's act. The command runs `helm` with the operator's
  values and creates no Secret: every Secret the chart names exists before, as
  `deploy/k8s/README.md` says.
- The command was proven against stand-ins, not on a cluster. Its first run on a cluster is an
  installation by a person, and the time it records is reported in
  `docs/runs/first-process-in-ten-minutes.md`.
- With the profile `ha` the first running pod of any role answers; each role holds the same
  command line.
- The measurement with a person new to Taktus (NEED-0034) is that person's act, not this command's.
