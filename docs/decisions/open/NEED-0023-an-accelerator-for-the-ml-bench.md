# NEED-0023 — An accelerator for the ML bench

**Kind:** access
**Raised in:** [#215](https://github.com/Jersyfi/taktus/pull/215), for issue #89
**Issue:** [#213](https://github.com/Jersyfi/taktus/issues/213)
**Needed by:** 2026-12-01
**Foreseeable since:** [#215](https://github.com/Jersyfi/taktus/pull/215), where the bench's work was split into a part that runs on an ordinary processor (#89) and a part that needs an accelerator (#210)

## 1. What is needed

One graphics processor — an accelerator for training models — that the ML bench may hold for some
hours at a time. The ML bench is the worker of Taktus that trains small models of its own. Its
first part now trains on an ordinary processor. Its second part, issue #210, must show the case the
worker contract was designed for: a training run that holds an accelerator for hours and returns a
model. That cannot be shown without one.

One accelerator with at least 16 GB of memory is enough. It need not be new or large; the models
are small. It needs to be reachable by Taktus's instance, and nothing else of yours needs to run on
it while a training holds it.

## 2. Why

Issue #210 verifies three things, and two of them need the accelerator: the bench passes the worker
conformance suite in a resource class that names an accelerator, and a training holds the
accelerator for hours, is stopped and resumed, and returns its model. Without it, #210 can build
the embeddings on an ordinary processor, and the second proof case of the worker contract
(ADR-0007) stays half proven.

## 3. By when

**2026-12-01**, so that #210 can be proven within the milestone `0.4.0`, whose completion asks for a
step that moves to a trained model.

If it is not there by then: #210 builds and proves what it can on an ordinary processor, its
conditions on the accelerator stay open, and the issue stays open with them. Nothing else waits.

## 4. How to provide it

Two ways. Either is enough.

**Way 1 — recommended: a node with an accelerator in the cluster Taktus runs on.** Taktus starts a
worker as a job in its cluster (`deploy/k8s/README.md`), so a node there is reached without
anything new.

1. Add a node with one accelerator to the cluster, or fit one into an existing node.
2. Install the accelerator vendor's device plugin for the cluster, so that a job can request the
   accelerator as a resource.
3. Label the node so that only jobs which request the accelerator are placed there:

   ```sh
   kubectl label node "<node>" accelerator=gpu
   ```

4. Allow the namespace where Taktus starts its jobs to request one accelerator: in its resource
   quota, a limit of one on the accelerator's resource name.
5. Write the node's name and the accelerator's model into the private note, under "accelerator
   for the ML bench".

Recommended because the cluster already runs Taktus's jobs, keeps its own backups and its own
limits, and the bench then runs there exactly as it would at a customer's.

**Way 2 — a separate machine with an accelerator**, yours or rented from a provider in the EU.

1. Install a container runtime and the vendor's driver, so that a container can use the
   accelerator.
2. Run the bench's image there (`workers/mlbench/Dockerfile`), listening on a port reachable from
   Taktus's instance and from nothing else.
3. Write the machine's address into the private note, under "accelerator for the ML bench".

A rented machine costs money for every hour it runs; switch it off between trainings. The
session spends nothing on it beyond what M2.8 allows, and only on a training a task needs.

## 5. What it must never be

- **Never shared with a workload of another system while a training holds it**: a measurement of
  hours of training is only true if the bench had the accelerator alone.
- **The node's name, the machine's address and the provider's account never in this repository**,
  an issue or a chat: they are the deployment's own names, and stay in the private note.
- **No credential of the cluster or of the provider is given to Taktus for this.** Taktus does not
  administer the platform it runs on (ADR-0025); it only places a job on what you prepared.

## 6. What happens next

Write in the issue: **"NEED-0023 is provided."** The next session records it first. Issue #210 then
runs its training on the accelerator, and records its duration and its consumption in its pull
request.

## 7. How to confirm

For way 1, from a machine with access to the cluster:

```sh
kubectl get nodes --selector accelerator=gpu --output name | wc -l
```

It prints `1` or more. For way 2, on the machine itself, the vendor's tool that lists the
accelerators prints one, with its memory, and no process using it.
