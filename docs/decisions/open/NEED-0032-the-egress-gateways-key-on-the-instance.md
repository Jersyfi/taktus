# NEED-0032 — The egress gateway's key on the instance

**Kind:** action
**Raised in:** [#547](https://github.com/Jersyfi/taktus/pull/547)
**Issue:** [#546](https://github.com/Jersyfi/taktus/issues/546)
**Needed by:** 2026-10-31
**Foreseeable since:** #324, which replaces each job's own egress proxy with one gateway of the instance

## 1. What is needed

A Secret with one random value, created on the instance's cluster in both of Taktus's namespaces,
and its name in the instance's private chart values. A coding step's unit reaches the internet
only through Taktus's egress gateway. From the next release on, the gateway is one Deployment for
the whole instance instead of one proxy per job. It admits each job by a token that Taktus signs
with this value. The chart refuses to install the new release without the Secret's name, so that
the instance never runs with a gateway nobody can sign for.

## 2. Why

Every coding step of P-03 reaches the coding agent's provider and the repository through the
gateway. Without the value, the release does not install, and the instance keeps the version it
runs. With it, a worker step starts one pod instead of three. The measurement that completes
#324 counts exactly that on the instance, before and after the release.

## 3. By when

Before the release candidate that carries #324 is installed. Nothing waits until then; the
current version runs as it is.

## 4. How to provide it

1. Draw a random value of at least 32 bytes on your own machine, for example with
   `openssl rand -base64 48`, and keep it in your password manager.
2. Create the Secret `taktus-gateway` with the key `key` holding that value in **both**
   namespaces of the instance: the control plane's namespace and the execution namespace. Use the
   same value in both. With the deployment identity, with `KEYFILE` the path of a file that
   holds the value and `NAMESPACE` each namespace in turn, this is
   `kubectl -n "$NAMESPACE" create secret generic taktus-gateway --from-file=key="$KEYFILE"`.
   Delete the file afterwards.
3. In the instance's private chart values, set:

   ```yaml
   execution:
     gateway:
       keySecret: taktus-gateway
       keyKey: key
   ```

4. Install the release candidate as usual. The chart mounts the value into the runner as
   `TAKTUS_EXECUTION_GATEWAY_KEY_FILE` and into the gateway's two pods.

The Secret's name is yours to choose; the values name whatever you chose.

## 5. What it must never be

Never the value itself in this repository, an issue, a log, a chat with a session, or the chart
values. The values name the Secret and its key, never what it holds. The value goes from your
password manager into the two Secrets and nowhere else.

## 6. What happens next

Once the release is installed, a session measures the pods each worker step starts, before and
after, by the steps on the pull request of #324, and records them there. Answer in the issue with
the sentence "NEED-0032: provided".

## 7. How to confirm

After the install, with `CONTROL` and `EXECUTION` the two namespaces, the first two commands
print `1` each, and the third shows the gateway with 2 of 2 replicas ready:

```bash
kubectl -n "$CONTROL" get secret taktus-gateway -o name | wc -l
kubectl -n "$EXECUTION" get secret taktus-gateway -o name | wc -l
kubectl -n "$EXECUTION" get deploy -l app.kubernetes.io/component=gateway
```
