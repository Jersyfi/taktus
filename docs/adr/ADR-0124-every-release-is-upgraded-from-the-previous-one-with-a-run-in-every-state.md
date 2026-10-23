# ADR-0124 — Every release is upgraded from the previous one, with a run in every state

**Status:** accepted · extends ADR-0093 (an upgrade beside the previous release) and ADR-0096 §6 (ring 4) · issue #445, DEC-0201

## Context

From `0.4.0` a business installs and operates its own instance (DEC-0201). The project never
acts on it. Every release must therefore upgrade that instance without losing a run, and without
anyone of the project there to repair it.

ADR-0093 keeps the schema working for the previous release's code during an upgrade. It does not
show that a run that waits survives the change of code. A run can wait in five ways: finished,
waiting for a person, parked in a long wait, halted at a limit, escalated after a failure. Each
keeps its place in the database, and the new release must read it and continue from there.
Nothing tested that. `deploy/docker/verify.sh` restarts the same build, not a newer one.

## Decision

### 1. One test, from the previous release to this checkout

`deploy/docker/upgrade.sh` starts the previous release from its own tag's compose files and its
published images. It leaves one run in each of the five states. It replaces the containers with
this checkout's, which migrate on start. It then checks:

- every run is in the state it was in, and its ledger's chain verifies;
- each run that waits continues as its operator would continue it — confirmed, its limit raised,
  resumed once the cause of its escalation is gone, or woken at its time — and finishes;
- no step that had completed before the upgrade starts again.

### 2. It runs on every release tag

The workflow `upgrade` runs it when a version tag is pushed, against the tag before it on the
same line of history (`git describe --tags --abbrev=0 <tag>^`). The previous images are pulled
from the registry the repository names (`vars.IMAGE_REGISTRY`), as the image workflow pushes them.
Without that variable the workflow says so and runs nothing. It can also be started by hand with
the tag to upgrade from. A person runs the same script locally with `make verify-upgrade`.

### 3. A failed upgrade test stops the release

A release whose upgrade test is red is not handed to any operator. The tag stays, because a tag
is never moved. The next release carries the repair, and its own upgrade test starts from the
last release whose test was green, named by hand.

## Alternatives

- **Test the upgrade on the chart, in a cluster.** Rejected for now: CI has no cluster, and the
  chart's upgrade differs from compose only in who runs the migration. The chart's pre-upgrade
  migration is rendered and checked by the chart's tests.
- **Test only the schema, as ADR-0093 asks.** Rejected: a schema that loads says nothing about a
  waiting run that the new code reads differently.
- **Run it on every pull request.** Rejected: it builds two releases and waits minutes for a
  parked run. A release is where the promise is made.

## Consequences

- Each release carries proof that the previous release's runs continue on it.
- A change that breaks a waiting run's continuation is found at its release, before any business
  upgrades to it.
- The administration guide's page *Upgrading* can promise what the test shows, and no more.

## Where this promise ends

- It covers one step: the previous tag on the same line of history to this one. An upgrade that
  skips a release is not tested.
- It covers the deployment on one machine. The chart's upgrade is covered only as far as its
  migration job is rendered and checked.
- It covers the five states named here, for processes built from `rule`, `wait` and `worker`
  steps. A run that waits on a connector or a model is not in it.
- It shows that runs continue. It does not show that every result is the same as it would have
  been without the upgrade.
