# NEED-0004 — The platform's current interface note

**Kind:** information
**Raised in:** [#22](https://github.com/Jersyfi/taktus/pull/22), which adds the needs request and the status report
**Issue:** [#21](https://github.com/Jersyfi/taktus/issues/21)
**Needed by:** 2026-10-12
**Foreseeable since:** [#9](https://github.com/Jersyfi/taktus/pull/9), which built the daemon and left `deploy/k8s` a placeholder for the platform

## 1. What is needed

A short written description of the platform Taktus will be deployed to, as it is **now** —
its shape, not its secrets. The platform has changed since it was last described, and that
description was never in this repository. The deployment — the cluster execution adapter, the
image build, the chart under `deploy/k8s` — must be built against the current interface, not
the old one. What is asked for is the list in section 4: how a workload is deployed there,
which keys its values file expects, under which **names** the secret parameters of
`CREDENTIALS.md` are supplied, which namespaces the instance gets, how outbound traffic is
controlled, and under which path the webhook arrives. Names and shapes only. Never a value.

## 2. Why

It unlocks the third pull request of the status file's plan: deployment on the target platform,
which `0.1.0` lists (the registry build and the chart) and which every later milestone runs on
— the 14 days of self-maintenance of `0.2.0` happen on a deployed instance, not on a laptop.
Without the note, a session would build the chart against the platform as it was described in
a mandate that is no longer current, and the owner would find out at the first deployment that
the values keys, the secret names or the egress mechanism are wrong. ADR-0025 says the
instance that develops Taktus may run on the platform it is deployed to; what that platform
looks like today is the one fact the repository does not hold.

## 3. By when

**2026-10-12**: one week after the first live run's credentials, so that the deployment pull
request can follow the live run without waiting.

If it is not there by then: the deployment pull request is not started. It is not built
against the old description, because a deployment built on a wrong interface is work that
must be thrown away — the very thing the blocking test of the decision mechanism exists to
prevent. `0.1.0` is then complete without a deployment (its criterion does not need one), and
`0.2.0` starts on the self-hosted two-container shape (`make up`) until the note arrives.

## 4. How to provide it

Write one document with the answers below. **It does not go into this repository**, which is
public: the names a deployment gives its secrets, its namespaces and its hosts are that
deployment's own business (`CREDENTIALS.md`: *deployment-specific names belong in the
operator's private configuration*). Two places work; the first is recommended because the
values file itself will need a home there:

- **A private repository** of yours — `Jersyfi/taktus-deploy`, private — with the note as its
  `README.md`. The session reads it with your `gh` login on your machine. Later the values file
  (with names, never values) lives there too, and this repository's chart refers to it by its
  keys.
- Or a **local file** in the checkout that git ignores: `deploy/k8s/local/PLATFORM.md`
  (`deploy/k8s/local/` is added to `.gitignore` by the deployment pull request; until then,
  keep it outside the checkout).

The note answers these, each in a line or a short table. Where you do not know, write
"unknown" — that is an answer too.

1. **The platform.** What it is (a Kubernetes distribution and its version, or something else),
   who operates it, and how a workload is put on it: a chart applied by hand, a GitOps
   controller watching a repository, a pipeline. If a repository is watched: which one, which
   path, which branch.
2. **The boundary.** The namespace (or the platform's equivalent) the Taktus instance is given,
   and any second namespace for execution units (the containers the coding worker runs in).
   Whether the instance may create pods in it, which is what the cluster execution adapter
   needs, or whether units must be started another way.
3. **The values keys.** If the platform expects a chart with a values file of a given shape:
   the keys it expects — image, replicas, resources, ingress, environment, secret references —
   or the file's schema, or an example values file with every value replaced by its type.
4. **The secret parameters.** For every parameter of `CREDENTIALS.md` the deployed instance
   needs — `database.url`, `credential.<name>` for the coding agent and the repository token,
   `credential.model_api_key`, the webhook signing secret, `otlp.headers` if telemetry is
   collected — how the platform supplies it: the mechanism (a Secret object mounted as a file,
   an external secret store synced into one, an operator-managed secret), the **name** of the
   Secret and the **key** inside it under which each parameter arrives, and the mount path.
   Names, never values. Taktus reads every secret from a file (`TAKTUS_<KEY>_FILE`), so the
   mount path is what the deployment needs.
5. **The database.** Whether PostgreSQL is provided by the platform (an operator, a managed
   service) or deployed with Taktus; how its connection URL reaches the instance (point 4);
   whether the instance may run its own migrations.
6. **Egress.** How outbound traffic is controlled: a network policy, an egress gateway, a
   proxy, nothing. Which hosts the instance must be allowed to reach — the repository host,
   the model endpoint — and how an allowlist is declared. The container adapter today runs its
   own egress proxy per job; on the platform the cluster adapter will use the platform's
   mechanism, and it needs to know which.
7. **Ingress and the webhook path.** The public URL under which the instance is reachable, and
   the path prefix if it is served under a sub-path (`TAKTUS_PATH_PREFIX`). Taktus serves the
   webhook intake at `<prefix>/intake/<channel>`; the repository's webhook must point at that
   URL, and the note says what the URL will be. Where TLS terminates.
8. **The image registry.** Where images are pushed, under which names, and how the platform
   pulls them (a pull secret's name, if one).
9. **Telemetry.** Whether an OTLP collector exists on the platform and its endpoint name; or
   none.
10. **What changed.** One paragraph on what is different from the last description, so that
    nothing built on the old one survives by accident.

## 5. What it must never be

- **Never a value.** No password, no token, no key, no certificate, no connection string with
  a password in it. The note is names, paths, mechanisms and shapes.
- **Never in this repository**, not even without values: the Secret names, the namespace and
  the hosts are one deployment's own names, and this repository is public. The deployment pull
  request refers to them by the parameters of `CREDENTIALS.md` and by values keys; the mapping
  from parameter to your name stays in your private place.
- **Never pasted into a chat or a session as text.** The session reads the note from the
  private repository or the local file. If a session asks you to paste the note, point it at the
  file.
- **Never an issue comment.** The issue is public with the repository.

Where it goes instead: the private repository or the ignored local file of section 4.

## 6. What happens next

Tell the session: **"NEED-0004 is provided; the note is at `<owner>/<repository>` (or: at
`<path>`)."** The session reads it there, confirms with section 7, records the outcome in this
record, and the deployment pull request is planned against it: the cluster execution adapter
with the platform's egress mechanism, the chart with the platform's values keys, the secret
mounts under the parameters of `CREDENTIALS.md`, the webhook URL. The webhook signing secret
is then raised as its own need, with the steps the note makes possible.

## 7. How to confirm

That the note is in a private place and complete, without revealing anything:

```bash
gh repo view Jersyfi/taktus-deploy --json visibility --jq .visibility
```

prints `PRIVATE`; and the note has an answer — a value, a shape or "unknown" — under each of
the ten points of section 4. A session confirms the same two facts and nothing else before it
records the outcome; the first real confirmation is the deployment pull request's own, when
`deploy/k8s` renders against the keys the note names.

## Outcome

**Provided:** 2026-09-23
**How:** **superseded, not answered.** The owner decided the target with the commission of that
day (DEC-0023) and gave a session read-only access to the platform instead of a written note.
The session inspected it and answered the ten points of section 4 itself.
**Confirmed by:** the inspection, read-only: nothing on the server was created, changed,
installed or restarted, and section 6 of the resulting note lists every command that was run.
Each of the ten points of section 4 has an answer: the platform and how a workload reaches it
(a Kubernetes distribution, push-based, no controller watching a repository — and the deployer
pattern the platform already uses for something else, which the plan copies); the boundary
(two namespaces, and the instance may create jobs in the second); the values keys (written as
the chart's interface in `deploy/k8s/README.md`); the secret parameters (every one mounted as
a file and read through its `TAKTUS_<KEY>_FILE` variable, and what is still missing is
NEED-0007); the database (a decision the plan makes, with ADR-0020's reason); egress (a network
policy controller that works, and *no* mechanism that can hold a job to a list of hostnames —
see below); ingress and the webhook path (the mechanism is there, the name is NEED-0008); the
image registry (public, pulled without a secret, and what changes if it is made private);
telemetry (none, and nothing fails without it); and what changed since the last description.
**Where the answers are:** outside this repository, in the operator's private note, because
they are one machine's names, addresses and figures and this repository is public — which is
what section 5 of this record asked for. The session told the owner the path. This repository
received only the generic requirements, as `deploy/k8s/README.md`.
**The one answer that changes the plan:** the platform can enforce a network policy and has
nothing that can enforce a list of **hostnames**. So `frame.allowed_hosts` is not a network
policy there and never could be: the plan puts a per-job egress proxy in a pod of its own, and
a default-deny policy that permits the job exactly one destination — the proxy. Where that
cannot be built, the adapter refuses to start a job whose frame names hosts rather than
starting it with an unenforced list.
**What replaces this need:** NEED-0007 (a kubeconfig for the deployment identity) and NEED-0008
(a public name for the instance), both raised in the same pull request with the steps. The
webhook signing secret is raised once the name exists, as this record's section 6 said it would
be.
**Recorded in:** [#40](https://github.com/Jersyfi/taktus/pull/40)
