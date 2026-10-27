# ADR-0136 — A first process comes from a gallery of open bundles, as a proposal with no version before it

**Status:** accepted · extends ADR-0091 (proposal, rehearsal, commissioning), ADR-0030 (the rehearsal), ADR-0026 (the autonomy statement) and ADR-0104 (tenants) · issue #405, UC-10.4

## Context

Issue #405 asks that a person new to Taktus, who is not technical, gets from installing Taktus
to a first rehearsed process in ten minutes, and that the time is measured. UC-10.4 states it as
a requirement. Four things stood in the way.

- **A proposal needed a version before it.** The plan dialogue of UC-1.10 offers a rehearsal of
  a proposal, and commissioning after it. A proposal was always made against the process's
  active version (ADR-0091 §1). A person's first process has none, so it could not go the path
  UC-1.10 built.
- **There was nothing to choose from.** The repository's blueprints describe departments of a
  business, and the one example that runs on a new instance confirms fixed values.
- **The install ended in commands.** After `make up`, the installation guide had a person type
  `taktusctl tenant create` and `taktusctl identity add` before the web app could be opened.
- **Nothing recorded the time.** A trial could only be timed by someone with a watch.

Two words are used below. A **gallery blueprint** is a directory of open files: a short
description in plain words, and the bundles of the processes it offers. A **choice** is a value
a person sets before a process is proposed: one of the inputs its bundle declares.

## Decision

### 1. The gallery is a directory of open files

The gallery is the directory `TAKTUS_GALLERY_DIRECTORY` names. Each directory under it that
holds a `gallery.yaml` is one gallery blueprint. `gallery.yaml` holds `kind: gallery`, which
tells `taktusctl bundle check` it is no process, the blueprint's `title`, whom it is `for`, and
a `summary`, in plain words. The blueprint's processes are the bundles
under its `processes/`, one file each, in the format every bundle has.

The instance reads the directory when it is asked for the gallery, and keeps nothing of it. A
blueprint removed from the directory is therefore gone from the gallery at the next reading.
Nothing else reads the directory. No process, no test outside the gallery's own and no setting
needs a gallery blueprint to exist. When the setting names nothing, or a directory that does not
exist, the gallery is empty, and the instance works as before.

The image carries the repository's `blueprints/gallery/` and names it by default. It holds three
gallery blueprints: a family, a club and a small business.

### 2. What the gallery offers is held to rules

A bundle is offered only where it passes the checks registration applies to a bundle on its
own: the same checks as `taktusctl bundle check` (ADR-0026, ADR-0014). A bundle is offered only
at autonomy level 1 or 2, with its reason (UC-10.3). A bundle that fails either is listed with
why it is not offered, and cannot be chosen. The gallery reads the bundle; it does not trust
what the description says about it.

Each offered process is shown with its name, its reason, its steps with method and reason, and
its choices. Each choice is one of the inputs the bundle declares that a schedule trigger of the
bundle gives, with the input's `description` as its label and the first such trigger's value as
its value. A process without a schedule trigger offers no choice.

### 3. Choosing makes a proposal

A person chooses a process and sets its choices. The instance writes each choice into the
`inputs` of every schedule trigger of the bundle that gives that input. A choice that names no
declared input is refused, and nothing is proposed. The changed bundle then becomes a proposal
through `Proposals.propose`, with `from the gallery: <title>` as its request. It is held to every
check a proposal is held to. Where the tenant has registered versions of a process with the same
identifier already, the proposal names the next free version.

A person who wants other choices chooses again. The earlier proposal stays open until it is
discarded.

### 4. A proposal may have no version before it

A proposal for a process that has no active version is made against no version. Its
`base_version` is absent. Its difference lists every step as added, and its autonomy before is
absent. ADR-0091 is otherwise unchanged:

- **Rehearsal.** The proposal is rehearsed as any proposal is (ADR-0030, ADR-0091 §3). A
  rehearsal that is given no inputs takes those its schedule trigger gives, and otherwise every
  declared input's `example`. A proposal with no version before it starts no evaluation
  (ADR-0134 §4): there is no version to compare it with.
- **Commissioning.** It is commissioned once its rehearsal finished, as any proposal is
  (ADR-0091 §4). It is refused as stale when the process has an active version by then. A
  first version registers without an approved raise, as a first version registered by hand
  does.

This holds for every proposal, not only for one from the gallery. `POST
/processes/{process_id}/proposals` with a bundle for a process the tenant does not have makes
one.

### 5. The surfaces

- `GET /gallery` lists the gallery blueprints, each with its processes as §2 shows them.
- `POST /gallery/{blueprint}/{process}/proposals` makes the proposal of §3. Its body holds the
  choices. It answers `201` with the proposal, `400` with every finding, and `404` for a
  blueprint or process the gallery does not hold.
- Both need an account key, as every read and act of the web app does (ADR-0119).
- The web app has a page `Gallery`. The start page leads to it while the tenant has no process.
  Choosing a process opens the plan dialogue of UC-1.10 on its proposal. That page also shows a
  proposal for a process that has no version yet.

### 6. One command installs, and starts the clock

`make start` is the one command of a first install on one machine. It runs, in order:

1. the secrets and the image build, as `make up` does;
2. the two containers, until the instance answers that it is ready;
3. `taktusctl first start`. On an instance that serves no tenant other than `default`, it
   creates a tenant and the identity `idn_admin` in it, and prints the account key once, with
   the web app's address. On an instance that serves another tenant already, it creates
   nothing and says so.
4. The clock. The command waits until the tenant's first rehearsal of a proposal has finished,
   reading it with `taktusctl first rehearsal` every five seconds. It then prints the time
   since step 1 started, and the time of each stage.

The command writes what it measured to `deploy/docker/first-process.json`, which git ignores:
when each stage began, from the host's clock and the run's own records; the machine's system,
architecture and processor count; and whether the time was within ten minutes. `Ctrl-C` stops
the clock, and the instance keeps running.

### 7. The path is also measured without a person

`make verify-first-process` installs a new instance under a compose project of its own, with
`make start`'s script. It then does what a person does in the web app, through the same HTTP
surface: it signs in with the printed key, reads the gallery, chooses a process and rehearses
its proposal. It reads the time the script recorded. It fails where the rehearsal did not
finish, or where the time was more than ten minutes. The nightly ring runs it, on a runner that
is a new machine. On a machine that built the image before, `TAKTUS_FIRST_NO_CACHE=1` builds it
as a new machine would: the base images pulled, and no cached layer used.

## Alternatives

- **The first process registered directly, then a proposal against it.** The first process would
  then have gone live before it was rehearsed, which UC-10.4 forbids.
- **The gallery inside the database, imported once.** It would not be removable by removing the
  files, and the instance would keep what an operator had taken out.
- **A gallery manifest listing every blueprint.** Removing a blueprint would then need an edit
  of the manifest as well. A directory per blueprint needs none.
- **Choices as pointers into any field of the bundle.** They could change a step's method or
  its autonomy past what the gallery checked. The bundle's own declared inputs are what a
  process already offers to vary.
- **A first sign-in in the browser, without a key.** Whoever reached the instance first would
  own it. An instance on a cluster may be reachable by others.
- **The clock in a separate script the person starts.** A person who forgets to start it is
  not measured. The clock is part of the one command.

## Consequences

- `Proposal.base_version` is optional, and `Difference.autonomy_before` too. A proposal is a
  document in its table (migration `0050`), so no migration is needed.
- `ProposalActs` rehearses and commissions a proposal with no version before it.
- The composition root gains `Gallery` (`composition/gallery.py`), the setting
  `TAKTUS_GALLERY_DIRECTORY`, and the HTTP routes of §5.
- `taktusctl first start` and `taktusctl first rehearsal`; `make start`, with
  `deploy/docker/start.py`; `make verify-first-process`, with `deploy/docker/first-process.sh`.
- The repository gains `blueprints/gallery/` with three gallery blueprints, and the image carries
  it.
- The web app gains the gallery page, and the plan dialogue shows a proposal for a new process.
- The installation guide starts with `make start`.

## Where this promise ends

The ten minutes are a measurement, not a guarantee. `make start` builds the image from the
source on the machine. That build takes the longest, and how long depends on the machine and
the network. A slower machine can take more than ten minutes, and the clock then says so. The
measured time ends when the rehearsal has finished; reading its result and commissioning it
come after.

`make start` and its clock serve one machine. On a cluster, the chart installs in one command
(#326), but no command creates the first tenant there, and no clock runs.

The gallery holds three typical situations. Its processes reach nothing outside Taktus: they
compose and check text from the person's choices. Connecting a person's own systems is UC-1.3.
A choice is one of a bundle's declared inputs; anything else is changed through the plan
dialogue's request in words, where the instance has a change process and a model (ADR-0091 §2),
or by a bundle handed over.

The gallery checks a bundle as `taktusctl bundle check` does. Three rules registration applies
are not among them: a credential that administers the instance's platform, a raise of an
autonomy level, and a version registered before with another content. A gallery bundle that
fails the first is refused when it is proposed, with the finding; the other two are met by §3
and §4.

`taktusctl first start` creates the first tenant once. It does not undo anything, and it does
not tell a person's first tenant from an operator's. Its account key is shown once in the
terminal, as `taktusctl identity add` shows one.

The measurement with a person is the person's, reported in the repository. The script records
the time; it does not observe the person, and the report names nobody (principle 14).
