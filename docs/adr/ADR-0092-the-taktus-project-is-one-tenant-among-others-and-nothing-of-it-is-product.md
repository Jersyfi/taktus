# ADR-0092 — The Taktus project is one tenant among others, and nothing of it is product

**Status:** accepted · from the owner's statement DEC-0188; the work is #313 (`0.3.0`) and #354 (`2.0.0`)

## Context
Taktus develops itself. It runs its development processes (P-01 to P-03), its self-operation
(S-01 and the others), the guides of its own repository and its own findings. Later it will also
license and bill its own customers (DEC-0188). All of that runs on an instance of the same
product that customers install.

Customers range from a person to an operator that hosts Taktus for others (`docs/vision/vision.md`).
The owner's rule is that the project's own development must never limit how a customer uses
Taktus. Nothing that concerns only the project may reach a customer.

The review of 2026-10-12 (`docs/research/2026-10-12-devops-review.md`, X1) found the separation
mostly clean. No blueprint ships in the image, no project process is scheduled by default, and the
product's decision register lives in the database. It also found leaks:

- **the budget seed:** every install calibrates its budgets from the project's coding-worker
  runs of 2026-09-23;
- **the guides manifest:** its default assumes this repository's layout;
- **the chart:** its default `model.outputCap` was measured against the project's endpoint;
- **the findings:** they take the shape of this repository's issue form;
- **help and error texts:** they name project processes.

## Decision

### 1. The project is a tenant like any other
Everything that belongs to the Taktus project is one of three things:

- **configuration** of an instance or of the project's tenant: values, limits, seeds, channels,
  paths;
- **a bundle** of the project's tenant: its processes, under `blueprints/`;
- **a document** of this repository.

None of it is product code, a default value of the product, or a migration's seed. A default of
the product is chosen for a customer who knows nothing of this repository.

### 2. What is measured on the project stays the project's
A figure measured on the project's runs — a budget seed, an output limit, a price — enters a
customer's instance only as data that instance's operator chooses to load. A fresh install starts
from the product's neutral rule. For budgets that rule is the doubled reservation of DEC-0034.

### 3. The project's business runs as its processes
The project's licensing, billing and customer administration are bundles of its tenant. They run
on the generic capabilities: accounting, the finance blueprint (P-11) and the connectors. A
capability the bundles need and the product lacks is added to the product in a form any tenant
can use, or not at all (#354).

### 4. A test holds it
`tests/architecture` fails on any of the following in `src/` or in the chart's default values:

- the project's process identifiers;
- its repository's path;
- its owner's name.

Comments that explain where a feature came from are exempt as long as they set no behaviour.

## Alternatives
- **A product mode for the project.** Rejected: it is the leak by design. A switch that changes
  the product for one tenant makes that tenant's needs the product's.
- **A fork for the project's own instance.** Rejected: the project would no longer run what its
  customers run, and Taktus developing itself would prove nothing.

## Consequences
- The budget seed becomes data the project's tenant loads, and a new install starts uncalibrated.
- The repository's own process (DEC, NTC and NEED records, the anchor page `anchors.taktus.md`,
  `docs/status.md`) stays a document of the repository and never a feature of the product. The
  product's decision requests and anchors are the generic form of it (`anchors.md`).

## Amendment — where each leak went (2026-10-13)

Issue #313 removed the leaks of the context. Each became a setting of the instance, without a
default that serves the project. The project's own values are documents of this repository,
which its operator loads. This amendment sets aside two sentences of earlier records:
ADR-0005's third amendment, point 4, says the product ships the seed of the first run, and
ADR-0046 §4 says a finding opens an issue labelled `task` in the sections of this repository's
issue form. Both are now the project's configuration.

### 5. Each leak, and the setting that replaced it
- **The budget seed.** The product ships no seed. `TAKTUS_BUDGET_SEEDS` names a file of seeds,
  each with its method, the capabilities it applies to, its source and its observations. Without
  it a worker nothing has measured reserves twice its estimate (DEC-0034). The project's seed
  is `docs/runs/first-run.seeds.yaml`.
- **The guides manifest.** `taktusctl guides` takes the manifest's path with `--manifest` or
  `TAKTUS_GUIDES_MANIFEST`, and refuses without one. The project's manifest is
  `docs/guides/guides.yaml`.
- **The chart's output limit.** `model.outputCap` defaults to `soft`, the setting's own default.
  The project's operator sets `hard` in the private values.
- **The findings.** `TAKTUS_FINDINGS_FORM` names a file with the form of a finding's issue.
  `TAKTUS_FINDINGS_LABELS` names its labels. Without them a finding takes the product's plain
  shape, with no label. The repository it goes to is the connector's, as before. The project's
  form is `.github/finding-form.md`, with the label `task`.
- **The change in dialogue.** The product named the project's process S-07 to turn a request in
  words into a proposal (ADR-0091 §2). `TAKTUS_CHANGE_PROCESS` names that process now. Without
  it a change is handed over as a bundle. The project sets `s07-change-in-dialogue`.
- **Help and error texts.** They name no project process. An example in a text uses a neutral
  name.

### 6. Files of configuration on a cluster
A setting that names a file needs the file in the pod. The chart's `configFiles` maps a file
name to its content and mounts it read-only at `/etc/taktus/files/<name>` in every role. It
carries no secret: a secret goes through `credentials`.

## Where this promise ends
- The amendment moves the project's values out of the product. It does not move them into a
  place the product reads by itself: the project's operator sets every one of them, and an
  instance whose operator forgets one runs with the product's neutral value.
- The test catches named leaks: identifiers, paths and names. It cannot catch a default that was
  chosen because it suits the project without naming it. That remains a matter for review.
- The project's experience still shapes the product, as any customer's would. This rule bounds how
  that experience arrives (as configuration, a bundle or a general feature). It does not bound
  whether it arrives.
- Documentation and examples may use the project as an example, marked as one.
