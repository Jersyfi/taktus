# DEC-0011 — No worker code in the control plane image

**Category:** DEFECT
**Raised in:** [#10](https://github.com/Jersyfi/taktus/pull/10), which adds the execution layer
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

Taktus is a control plane: it decides what runs and has it run. The thing that runs — a
*worker*, which executes tasks such as running shell commands or writing code — is a separate
program behind an open contract. The architecture says so in several places: a worker is "a
separate deployable", the control plane "bundles no foreign runtime", and execution is isolated
from the control plane on purpose, because a worker executes foreign code.

The previous pull request packaged the control plane as one container image and, for
convenience, put the reference worker into the same image as an optional third service of the
deployment file. The documentation described the result as "two containers", which was true of
the control plane and said nothing about what those two containers can do.

Two things were wrong with that.

**Security.** A worker's purpose is to execute foreign code. Shipping its code inside the
control plane image means it is present even when it is not started. A compromised control
plane then finds a ready-made command execution program in the tier that is deliberately not
the one that runs foreign code. The isolation drawn at the deployment level was undone at the
image level.

**Product.** What ships becomes the default. A contract whose reference implementation lives
inside the product is on the way to no longer being a contract, and the first guiding
principle — an orchestrator, not another tool landscape — is never violated in one large step.

## 2. Why you are being asked

You are not. No row of `anchors.md` §1 applies: nothing about the product's scope, its
releases, its licence or its public claims changes. The repository's own documents stated one
thing (workers are separate deployables, the control plane bundles no runtime) and the image
did another. That is row D6 of §2: a contradiction inside the repository, corrected and
recorded here. The correction changes packaging, not what the software does when it runs: the
same worker answers the same contract from its own image.

## 3. What you must decide

Nothing. The record exists so that no worker is ever added to the control plane image "for
convenience" again, and so that "two containers" is read as what it is: the control plane,
not the whole installation.

## 4. What you need to know to decide

- **Control plane image.** The one image that runs every role of Taktus, selected at start.
  It now contains the control plane, the contracts, the migrations and the examples — and no
  file from `workers/`. An architecture test checks the build recipe, and the end-to-end
  check inspects the built image.
- **Worker image.** Every worker builds its own image from this repository
  (`workers/script/Dockerfile`, `workers/claudecode/Dockerfile`). The control plane reaches a
  worker through the execution port: by endpoint, as a process, or as a container it starts.
- **Deployment file.** `deploy/docker/compose.yml` is the deployment shape: Taktus and
  PostgreSQL, no worker. It says how a worker is configured. A separate development file,
  `compose.reference-worker.yml`, layers the reference worker over it for trying the system
  out and for the end-to-end check.
- **What "two containers" means.** Two containers for the control plane, plus one execution
  unit for every process that has a `worker` step. A process built only from `rule`,
  `statistics`, `wait` and `human` steps needs none, and method maturation moves processes in
  that direction over time.

## 5. Options

None for the owner. What the session did: gave the reference worker its own image; removed the
worker from the control plane image and from the deployment file; added the development file
that brings the worker up; added a check that fails when the control plane image contains
worker code; corrected `README.md` and `deploy/docker/README.md` to state what two containers
can do and what a process with a worker step needs in addition.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object to the correction: "Reopen DEC-0011" in an issue, with the reading
you hold.

## Outcome

**Corrected:** 2026-09-18
**What was wrong:** the reference worker shipped inside the control plane image and as an
optional service of the deployment file, while the architecture states that a worker is a
separate deployable and the control plane bundles no runtime; `README.md` described the
installation as "two containers" without saying that a process with a worker step needs an
execution unit in addition.
**Why it was wrong:** a worker executes foreign code, and code that is in the image is present
even when it is not started — a compromised control plane finds a command execution program
in the tier that is deliberately not the hostile one; and what ships becomes the default, so a
reference implementation inside the product erodes the contract.
**What it now says:** `deploy/docker/Dockerfile` copies nothing from `workers/`
(`tests/architecture` checks the recipe, `deploy/docker/verify.sh` the built image);
`workers/script/Dockerfile` is the reference worker's own image; `deploy/docker/compose.yml`
is the deployment shape, Taktus and PostgreSQL, and states that a worker is configured by
endpoint or started by the execution port; `deploy/docker/compose.reference-worker.yml` is the
development layer that brings the reference worker up (`make up-dev`); `README.md` and
`deploy/docker/README.md` state that two containers are the control plane, that every process
with a `worker` step needs one execution unit in addition, and that a process without such a
step needs none.
**What changed in substance:** nothing the software does when it runs. The same worker answers
the same contract; only where its code lives and how it is started changed.
**Recorded in:** [#10](https://github.com/Jersyfi/taktus/pull/10)
