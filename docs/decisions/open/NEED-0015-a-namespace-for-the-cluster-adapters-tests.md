# NEED-0015 — A namespace for the cluster adapter's tests

**Kind:** access
**Raised in:** [#119](https://github.com/Jersyfi/taktus/pull/119)
**Issue:** [#117](https://github.com/Jersyfi/taktus/issues/117)
**Needed by:** 2026-10-20
**Foreseeable since:** [#119](https://github.com/Jersyfi/taktus/pull/119), which builds the cluster execution adapter (#65); raised the same day

## 1. What is needed

A namespace on your cluster kept for one purpose: the tests that run the cluster execution
adapter against a real cluster. In it, an account with exactly the permissions Taktus's own
account will have in the execution namespace, and a kubeconfig file for that account. Plus the
reference worker's image where the cluster can pull it, and a place to run the tests from that
reaches the cluster's service addresses.

## 2. Why

The cluster execution adapter starts every worker step's unit as a Job in the cluster
(`deploy/k8s/README.md` §7). Its tests run in two layers. The first runs everywhere, against a
fake of the cluster's API, and proves what the adapter asks the cluster for. The second asks a
real cluster and checks from inside the job what the job can see and reach: no credential on a
filesystem, no service-account token, a read-only root filesystem, no capability, a host
outside the frame refused, nothing reachable without a proxy, a memory and a wall-clock kill.
Only the second layer shows that the cluster does what the adapter asked. Without this need it
skips, and says so in every test summary.

## 3. By when

**2026-10-20**, with the other needs of the deployment, so that the adapter has run on the real
cluster before the instance starts its first worker step there.

If it is not there by then: the instance can still be installed, and its worker steps would run
on an adapter proven against a fake only. A difference between the fake and the cluster — a
policy that does not hold, a field the admission refuses — would be found by the first real
assignment instead of by a test.

## 4. How to provide it

Everything below is run by you, once, with an account that may create namespaces. Every name
in angle brackets is yours and stays out of this repository.

1. **Create the namespace** and label it for the Pod Security level `restricted`:

   ```bash
   kubectl create namespace <test namespace>
   kubectl label namespace <test namespace> \
     pod-security.kubernetes.io/enforce=restricted \
     pod-security.kubernetes.io/audit=restricted \
     pod-security.kubernetes.io/warn=restricted
   ```

2. **Create two service accounts in it**: one the tests act as (`<tester>`), and one the jobs
   run as (`<runner>`), which holds no Role and mounts no token:

   ```bash
   kubectl -n <test namespace> create serviceaccount <tester>
   kubectl -n <test namespace> create serviceaccount <runner>
   kubectl -n <test namespace> patch serviceaccount <runner> \
     -p '{"automountServiceAccountToken": false}'
   ```

3. **Give `<tester>` exactly the Role of `deploy/k8s/README.md` §1**, in this namespace only:

   ```bash
   kubectl -n <test namespace> create role taktus-execution \
     --verb=create,get,list,watch,delete --resource=jobs.batch
   kubectl -n <test namespace> patch role taktus-execution --type=json -p '[
     {"op":"add","path":"/rules/-","value":{"apiGroups":[""],"resources":["pods","pods/log"],"verbs":["get","list"]}},
     {"op":"add","path":"/rules/-","value":{"apiGroups":[""],"resources":["secrets","services"],"verbs":["create","delete"]}}]'
   kubectl -n <test namespace> create rolebinding taktus-execution \
     --role=taktus-execution --serviceaccount=<test namespace>:<tester>
   ```

4. **Apply the network policies of `deploy/k8s/README.md` §5** to the namespace: one that
   denies everything in and out for every pod, and the exceptions by the labels the adapter
   sets. Where the section says "from the control plane's namespace", allow ingress to
   `taktus/role: unit` from the place the tests run (step 7). Until the chart (#64) renders
   these policies, they are written by hand from that section; the chart's own output can
   replace them once it exists.
5. **Issue a token for `<tester>`** and write a kubeconfig with the cluster's interface address,
   its certificate authority, the token, and a context whose namespace is `<test namespace>`.
   Keep it readable by you alone (`chmod 600 <the file>`).
6. **Make the reference worker's image pullable by the cluster**: the image CI publishes (#64),
   or one built from `workers/script/Dockerfile` and pushed where the cluster pulls from.
   Optionally the same for `tests/adapters/execution/hog/`, which the memory-kill test needs.
7. **Choose where the tests run**: somewhere that reaches the cluster's service addresses — a
   pod in the control plane's namespace, as the control plane itself does, or the node. A
   workstation outside the cluster does not reach them.
8. **Name everything there by path and by name, never by content**, in `.env`:

   ```bash
   TAKTUS_CREDENTIAL_CLUSTER_TEST_KUBECONFIG_FILE=<the path of the kubeconfig>
   TAKTUS_TEST_CLUSTER_NAMESPACE=<test namespace>
   TAKTUS_TEST_CLUSTER_WORKER_IMAGE=<the reference worker's image>
   TAKTUS_TEST_CLUSTER_HOG_IMAGE=<the hog image, optional>
   ```

## 5. What it must never be

- **Never the instance's own execution namespace.** The tests create and delete jobs; they
  belong in a namespace where nothing else runs.
- **Never more than the Role of step 3.** No read of a Secret, no `pods/exec`, no cluster role.
  The tests prove that the adapter works within that Role; a wider one would hide a call
  outside it.
- **Never pasted into a chat, a session, an issue or a pull request**, and never committed. The
  kubeconfig holds a token. `.env` holds its path; git ignores `.env`.
- **Never the deployment identity's kubeconfig (NEED-0007)** and never the cluster
  administrator's.

## 6. What happens next

Tell the session: **"NEED-0015 is provided; the cluster test settings are named in `.env`."**
The session runs `uv run pytest tests/adapters/execution/test_kubernetes_cluster.py` from the
place of step 7, records the outcome in the need, and fixes what the real cluster shows.

## 7. How to confirm

Without revealing anything: the account may create jobs and may not read a Secret.

```bash
KUBECONFIG=<the path> kubectl auth can-i create jobs.batch --namespace <test namespace>
KUBECONFIG=<the path> kubectl auth can-i get secrets --namespace <test namespace>
```

The first prints `yes`, the second `no`. Then the tests themselves: run from the place of step
7, they no longer skip, and every one of them passes or names what failed.
