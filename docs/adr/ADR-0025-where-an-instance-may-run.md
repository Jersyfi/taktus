# ADR-0025 — Where an instance may run

**Status:** accepted · applies ADR-0013 C and ADR-0020 to the platform an instance runs on

## Context
An instance of Taktus runs on some infrastructure: a home server, a cluster, a platform that
someone operates. Taktus at level 4 also *administers* infrastructure — it is one of the things a
department does, and the `it-operations` blueprint (`0.7.0`) is built for it. The two facts meet
in one question: may the instance that administers a platform run on that platform?

The question has been answered case by case so far, each time from scratch: the development
instance of the Taktus project may run on the platform it is deployed to; a later instance that
would manage that platform's tenants, quotas and network policies should not. Each answer was
right, and each was given without a rule to derive it from. A question answered from scratch is
answered differently the third time.

ADR-0013 C says that Taktus is repairable without Taktus. An instance that runs on
infrastructure it administers can break that infrastructure, and with it the path its own repair
would travel: a faulty change to the cluster's network policy takes down the pod that would
revert it. That is the failure the rule below prevents, and it is the only one it needs to
prevent.

ADR-0020 says that two instances share nothing: no database, no secret store, no connection.
That is what makes the second half of the rule safe.

## Decision

### 1. The rule
**No instance runs on infrastructure that it administers itself.**

*Administers* means: the instance holds credentials that can change the infrastructure — create
or delete namespaces, change quotas, network policies, node pools, storage classes, the
platform's own configuration — and runs processes that use them. Reading the platform's state
is not administering it. Deploying a workload into a namespace the instance was given is not
administering the platform either; that is using it.

### 2. What is allowed
Running on infrastructure that **anyone other than this instance** administers is allowed —
a person, an organisation, or a different Taktus instance — provided the running instance has,
on that infrastructure:

- its own namespace, or the platform's equivalent boundary;
- its own database (ADR-0002, ADR-0020);
- its own credentials, which reach nothing outside that boundary.

The three conditions are about **the boundary the instance is given**, not about how many
clusters, machines or platforms exist. A second cluster is one way to draw a boundary and is
never what the rule is about; two namespaces on one cluster, with the administrator outside
both, satisfy §1 exactly as well.

Where the administrator is another Taktus instance, it sees this one's namespace as one
workload among many and never calls into it (ADR-0020 §3). Where the administrator is a person
or an organisation, the same holds by their own discipline, and §1 is unaffected either way:
what §1 forbids is an instance administering its *own* ground.

*Amended 2026-09-23 (DEC-0024): the section named only "a different instance" as the
administrator, so the ordinary case — a platform a person operates — was permitted by §1 and
described nowhere.*

### 3. Two consequences, from one rule
- **The instance that develops Taktus** manages a repository and administers no infrastructure.
  It may run on the platform it is deployed to. Its credentials reach the repository and its own
  namespace, nothing else.
- **A later instance that administers that platform** — the one the `it-operations` blueprint is
  for — runs outside it: on other infrastructure, or on a platform that a third instance
  administers, under the same rule.

Neither is a special case. Both follow from §1, and the next question of this kind is answered
by §1 too.

- **A worked example, 2026-09-23 (DEC-0023).** The instance that develops Taktus runs on the
  owner's integration server, in a Kubernetes cluster the owner administers: one namespace for
  the control plane, one for the execution units, and a third namespace beside them that runs
  something else of the owner's. Taktus administers nothing there — its service account may
  create jobs in the execution namespace and read their logs, and nothing else — so §1 is
  satisfied and §2 describes the arrangement. The same record says what would change the
  picture: a workspace holding code the owner does not own, Taktus developing the product that
  runs beside it, or a move to production.

### 4. What the rule does not say
It does not say that an instance may not run in a container or a pod. It says nothing about
tenants: tenants are inside one instance and share its infrastructure by design (ADR-0020). It
does not forbid an instance from *observing* the platform it runs on — reading metrics, reading
its own resource usage — because observing changes nothing.

## Alternatives
- **No rule; decide per deployment.** The situation today. It works while one person holds every
  deployment in their head, and stops working the first time two people, or a person and a
  session, answer differently.
- **No instance runs on a platform that any Taktus instance administers.** Simpler, and wrong in
  the direction that costs the most: it would forbid the development instance from running on
  the project's own platform, for no gain. The blast radius ADR-0013 C worries about is an
  instance breaking *its own* ground; another instance's ground is another instance's blast
  radius, and ADR-0020 already keeps them apart.
- **Allow self-administration with extra safeguards** — a break-glass account, a second cluster
  for repair. Every safeguard is a second path that must be exercised as often as the first, and
  ADR-0013 C already asks for a manual repair path; a rule that needs no safeguard is cheaper
  than a safeguard that needs exercise.

## Consequences
- The operating documentation of the project describes where each instance runs, and why, by
  reference to §1 rather than by assertion.
- A process that would give an instance credentials for the infrastructure it runs on is refused
  at planning time once governance exists (`0.2.0`); until then, the rule is applied by the
  person who configures the instance.
- The `it-operations` blueprint states where its instance runs before it states anything else.

## Where this promise ends

The rule is applied by the person who configures an instance; refusing a process that would
give an instance credentials for its own infrastructure is `0.2.0`. "Administers" is defined
by the credentials an instance holds, and a credential that is broader than its holder knows —
a platform token with rights nobody listed — administers more than the rule sees. Two
instances on one platform are kept apart by the platform's boundary, which the platform
enforces, not Taktus.

The rule says nothing about **whose code runs inside the instance**. It keeps an instance from
breaking its own ground; it does not ask whether the workspace of a job holds code the owner
wrote or code a stranger did, and that question decides how strong the boundary around a job
must be. DEC-0023 answers it for one deployment and names what would change the answer; this
ADR does not answer it at all. It also says nothing about **what else shares the platform**: a
namespace of one's own is a boundary against workloads, not against a node running out of
memory.
