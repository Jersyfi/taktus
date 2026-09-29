# DEC-0023 — Where Taktus runs, and what separates it from what it builds

**Category:** NON-BLOCKING
**Raised in:** [#40](https://github.com/Jersyfi/taktus/pull/40), which records the target and writes the deployment plan
**Issue:** none; the owner gave the answer with the commission, and the record carries it

## 1. What this is about

Taktus has to run somewhere. Two questions come with the place, and they are usually answered
at the same time and then confused with each other afterwards.

The first is **where**: which machine, which platform, who operates it. The second is **what
separates the part of Taktus that decides from the part that executes**. Taktus's coding worker
runs an agent that writes and runs code. Code that writes code is, from the point of view of
the machine underneath, foreign code: nobody reviewed it before it ran. The usual answer to
foreign code is to put a boundary between it and everything else, and the strongest boundary
short of a second machine is a kernel boundary — a sandbox with a kernel of its own, or a
second cluster.

An earlier plan for this project had exactly that: the control plane in one place and the
execution units behind a kernel boundary, because the coding worker runs foreign code.

## 2. Why you are being asked

You are not, any more — you answered it with the commission of 2026-09-23, and this record
carries the answer so that it is findable and so that the reasoning does not have to be
reconstructed the next time somebody asks. The record exists for the second half: **what would
change the picture**, written down now, so that today's situation is not later mistaken for a
general rule.

The placement of an instance is governed by ADR-0025, whose rule is about who administers what
runs. The rule permits this arrangement; it did not describe it, and the correction is
DEC-0024.

## 3. What you must decide

Where the Taktus instance runs, and whether the coding worker's execution units need a
boundary stronger than a container from the control plane beside them.

## 4. What you need to know to decide

- **Whose code and whose data.** The repository Taktus develops is yours. The issues it reads
  are yours, the branches it writes are in your repository, and the machine is your integration
  server. There is no third party's code in the workspace and no third party's data on the
  disk. The coding agent is not adversarial; it is unreviewed, which is a different thing.
- **What a kernel boundary would protect.** It protects the host and everything else on it
  from a job that breaks out of its container. That is worth paying for when a break-out
  would reach something that is not yours, or something you cannot rebuild. Here it would
  reach an integration server of yours that is rebuilt from a chart.
- **What it would cost.** A second cluster to operate, or a kernel-isolating runtime installed
  on the node. The read-only inspection of 2026-09-23 found neither: none of the runtimes the
  node offers isolates a kernel. So the earlier plan would have begun with an installation, and
  that installation would have to be maintained and exercised like everything else that stands
  between Taktus and its own repair (ADR-0013 C).
- **What is still needed, whatever the answer.** A container boundary that is actually set up:
  a namespace of its own for execution, a restricted pod-security policy, a default-deny
  network policy in both directions, no service-account token mounted into a job, a real CPU,
  memory and deadline limit on every job. None of that is a kernel boundary and all of it is
  the difference between "in a container" and "contained".
- **What else is on the machine.** Another integration environment of the owner's runs in a
  namespace of its own on the same cluster, with its own database and its own network policy.
  Taktus does not administer it and does not reach into it. Which environment that is, and
  every other name on that machine, is in the operator's private note and not here: this
  repository is public (`CREDENTIALS.md`).

## 5. Options

### Option A — one cluster, two namespaces (recommended)

Taktus runs on your integration server, in its Kubernetes cluster: the control plane in one namespace, the
execution units in a second, and the two separated by a namespace boundary, a restricted
admission policy, a default-deny network policy and per-job limits. What already runs on that
cluster stays in its own namespace beside them.

For: the boundary matches the risk. Both the code and the data are yours, on your own
integration server, so a kernel boundary protects nothing that is at risk. One cluster to
operate, one thing to repair, and the repair path does not run through a second platform.
Against: a break-out from a job container reaches the node, and the node also carries the
other integration environment. The mitigation is that that environment is rebuildable and
holds no production data, and that every job is small, short and limited.

### Option B — a kernel boundary between the control plane and execution

Execution units run under a kernel-isolating runtime, or in a second cluster of their own.

For: a break-out reaches nothing. It is the right answer the day the workspace holds somebody
else's code.
Against: it buys isolation against a risk that is not present, and pays for it with a
component that must be installed, maintained and exercised on a machine that has neither today.
It also puts a second platform in the path of Taktus's own repair, which ADR-0013 C spends its
whole argument avoiding.

### Option C — execution off the machine entirely

The coding worker runs somewhere else — a hosted runner, a separate machine — and the control
plane calls it.

For: nothing shares a kernel with the agent.
Against: it is Option B's cost plus a network boundary, and it makes the run depend on a
second operator. It is where this goes if the coding worker ever processes a repository that
is not yours, and it is not where it starts.

## 6. What is blocked

Nothing. The deployment plan (`deploy/k8s/README.md`) is written against the answer, and it is
the specification for the next pull request.

## 7. How to answer

Answered. To change it: "DEC-0023, Option B" in an issue, with which of the three situations
below has arrived.

## Outcome

**Decided:** 2026-09-23
**Answer:** Option A. Taktus runs on the owner's integration server, in its Kubernetes cluster, with the
control plane and the execution units in the same cluster and in namespaces of their own. The
owner's other integration environment runs in a third namespace on the same cluster; Taktus
does not administer the cluster and does not reach into that namespace.
**Reasoning given:** the earlier plan put a kernel boundary between the control plane and
execution because a coding worker runs foreign code. Here both the code and the data are the
owner's own, on his own integration server, so that boundary protects nothing that is at risk.
What remains necessary is the container boundary done properly — its own namespace, a
restricted admission policy, default-deny in both directions, no mounted service-account token,
a limit and a deadline on every job — and that is what the deployment plan specifies.
**What would change the picture**, each one on its own enough to reopen this:

1. **Taktus processing code from a repository the owner does not own.** The moment a workspace
   holds somebody else's code, "the code is ours" stops being true and the boundary has
   something to protect.
2. **Taktus developing the product that runs beside it.** Then the thing Taktus can break and
   the thing running next to it are the same product, and a mistake in the first reaches the
   second.
3. **A move to production**, which the owner will call. An integration server that is rebuilt
   from a chart and a production system are not the same risk, and this answer was given
   about the first.

Until one of the three arrives, the arrangement above is not a general rule about clusters: it
is a judgement about *whose* code and *whose* data are in the workspace. ADR-0025 is corrected
to say that plainly (DEC-0024).
**Recorded in:** [#40](https://github.com/Jersyfi/taktus/pull/40)
