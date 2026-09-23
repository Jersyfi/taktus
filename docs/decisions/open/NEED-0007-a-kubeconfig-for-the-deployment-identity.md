# NEED-0007 — A kubeconfig for the deployment identity

**Kind:** access
**Raised in:** [#40](https://github.com/Jersyfi/taktus/pull/40), which records the target and writes the deployment plan
**Issue:** [#41](https://github.com/Jersyfi/taktus/issues/41)
**Needed by:** 2026-10-20
**Foreseeable since:** [#40](https://github.com/Jersyfi/taktus/pull/40), the pull request that planned the deployment against a platform inspected for the first time; raised the same day

## 1. What is needed

A way for the deployment to reach your cluster's Kubernetes interface that is **not a shell on
the machine**: a Kubernetes service account in the namespaces Taktus is given, a token for it,
and the cluster's certificate authority — the three things a `kubeconfig` file is made of.
Whoever installs Taktus, a person running the install command or the repository's own pipeline,
uses that file and nothing else.

It is *not* the identity Taktus runs as. That is a second, much narrower account which the
chart creates and nobody has to provide: it may create jobs in one namespace and read their
logs, and nothing else. Keeping the two apart is the point (ADR-0025: an instance never
administers the infrastructure it runs on, and an account that can change Taktus's own
deployment would be administering it).

## 2. Why

The deployment is the next pull request but one, and it is a chart applied to a cluster. There
is no controller on the platform watching a repository, so the chart is *pushed*: someone runs
the install command against the cluster's interface, and that needs a credential for it.

The read-only inspection of 2026-09-23 found that the interface **is reachable from outside**
and answers "unauthenticated" to anyone without a credential. That is the good case: the
deployment can run from a workstation or from the pipeline, and needs no account on the machine
at all. Today the only way in is a shell as root, which is more than a deployment should ever
hold and cannot be given to a pipeline.

You already have exactly this shape in the same cluster for something else, which is why the
ask is small: a service account with a namespaced role, bound in one namespace, used by a
pipeline. This one is the same thing for Taktus's namespaces.

## 3. By when

**2026-10-20**, a week before the deployment pull request is planned to start, so that it is
built and tried against the real interface rather than against an assumption.

If it is not there by then: the deployment pull request writes the chart and cannot install it
anywhere, so nothing about it is proven until it is. A session will not fall back to the root
shell: a deployment that works only from a shell nobody should hold is not a deployment, and
the whole point of the arrangement is that the credential is narrow enough to live in a
pipeline.

## 4. How to provide it

Two namespaces, one service account, one role, one binding, one file. Everything below is run
by you on the machine, once; nothing in it is a value this repository ever sees.

1. **Choose the two namespace names** — one for the control plane, one for the execution units
   — and create them. Their names are yours and stay out of this repository; the chart takes
   them as values.
2. **Create a service account** in the control plane's namespace, named for what it is:
   something like "deployer".
3. **Give it a namespaced Role, bound with a RoleBinding, in the control plane's namespace
   only.** The verbs it needs, and no others:

   | Resources | Verbs |
   |---|---|
   | `secrets`, `configmaps`, `services`, `serviceaccounts`, `persistentvolumeclaims` | `get`, `list`, `watch`, `create`, `update`, `patch`, `delete` |
   | `deployments`, `statefulsets` (`apps`), `jobs` (`batch`) | the same |
   | `roles`, `rolebindings` (`rbac.authorization.k8s.io`) | the same — the chart creates Taktus's *own* narrow account |
   | `networkpolicies` (`networking.k8s.io`) | the same — the chart creates the default-deny policies |
   | `ingresses` (`networking.k8s.io`) | the same |
   | `pods`, `pods/log`, `events` | `get`, `list`, `watch` only |

   A second RoleBinding of the same Role in the execution namespace, so that the chart can
   create what belongs there. **No ClusterRole**, no access to nodes, no access to any other
   namespace.
4. **Issue a token for the account.** A long-lived one bound to a Secret if you want one file
   that keeps working; a short-lived one if you would rather mint it per deployment. Either is
   fine; say which when you close the issue, because it decides whether this need returns.
5. **Write a `kubeconfig` file** with the cluster's public interface address, the cluster's
   certificate authority (the interface presents its own, which no public trust store knows),
   the token, and a context that selects the control plane's namespace. Keep it readable by you
   alone:

   ```bash
   chmod 600 <the file>
   ```

6. **Check it works from somewhere that is not the machine** — your workstation is the right
   place, because that is the arrangement being proved:

   ```bash
   KUBECONFIG=<the file> kubectl auth can-i --list --namespace <the control plane namespace>
   ```

7. **Tell the repository where it is**, by path and never by content, in `.env`:

   ```bash
   TAKTUS_CREDENTIAL_DEPLOY_KUBECONFIG_FILE=<the path>
   ```

   The name follows the one pattern every credential follows (`CREDENTIALS.md`, DEC-0018).

## 5. What it must never be

- **Never pasted into a chat, a session, an issue or a pull request.** It contains a token. A
  session that receives it cannot un-receive it, and this repository is public.
- **Never committed**, and never in a values file that is committed. `.env` holds the path;
  git ignores `.env`.
- **Never the cluster's own administrator kubeconfig.** The file your distribution writes for
  the cluster administrator is the whole cluster; this account is two namespaces. Copying that
  file would be the fastest way to break ADR-0025 with a single `cp`.
- **Never a ClusterRole binding**, however convenient a wildcard looks while something does
  not work. If the deployment needs a permission the table does not have, that is a change to
  the plan and to this record first, and to the role second.
- **Never the identity Taktus runs as.** That account is created by the chart and reaches one
  namespace's jobs and their logs.

Where it goes instead: the file of section 4, readable by you alone, and its path in `.env`.

## 6. What happens next

Tell the session: **"NEED-0007 is provided; the kubeconfig is named in `.env`."** The
deployment pull request then renders the chart and installs it against your cluster with that
file, from a workstation, without touching the machine. The same file is what the repository's
pipeline would later hold as its one deployment secret, if you decide the pipeline should
deploy — which is its own decision and not this one.

## 7. How to confirm

Without revealing anything — the first prints what the account may do in its namespace, the
second that it may **not** reach the cluster at large. Both answers are the point:

```bash
KUBECONFIG="$(sed -n 's/^TAKTUS_CREDENTIAL_DEPLOY_KUBECONFIG_FILE=//p' .env)" \
  kubectl auth can-i create deployments --namespace <the control plane namespace>
```

prints `yes`; and

```bash
KUBECONFIG="$(sed -n 's/^TAKTUS_CREDENTIAL_DEPLOY_KUBECONFIG_FILE=//p' .env)" \
  kubectl auth can-i list nodes
```

prints `no`. A `yes` to the second means the account is wider than the plan and the role needs
correcting before anything is installed with it.
