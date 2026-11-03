# NEED-0037 — A connect key for a worker that connects outbound

**Kind:** action
**Raised in:** the branch `concept/package-b` (package B, built in concept mode, DEC-0222), for issue #625
**Issue:** [#649](https://github.com/Jersyfi/taktus/issues/649)
**Needed by:** 2026-11-27
**Foreseeable since:** the branch `concept/package-b--workers`, where the control plane began to host the worker contract's outbound binding (ADR-0156)

## 1. What is needed

One random value, the **connect key**, in two places: in the instance's secret store under the
parameter `connect.key` of one worker configured as `connected`, and in the file that worker
reads. The worker is the reference worker (`workers/script`), run once outside the cluster so
that it reaches the instance only outbound. Nobody provides the value from elsewhere: you
generate it.

## 2. Why

Issue #625 is verified on the project's own instance only when the instance's conformance
suite runs over the outbound binding for a connected worker and its record names the binding
(ADR-0044, ADR-0156 §5). The code and its tests are in package B; the record on the instance
needs a worker that actually connects, and the key that admits it.

## 3. By when

**2026-11-27**, so that the record exists before `0.6.0` closes. If it is not there by then,
#625 stays proven by tests on two local instances only, and nothing else waits.

## 4. How to provide it

**Step 1 — the value.** Done by the session on 2026-11-03 under NEED-0040 (DEC-0224): the key is
the item `taktus-connect-key-connected-reference` in the vault `Development`. Nobody typed or saw it.

**Step 2 — the instance.** Put the key into the instance's secret store as the connect key of a
worker named `connected-reference` (`CREDENTIALS.md`, row *Connect key of a connected worker*).
From 1Password, without the value passing through a file or a screen. Name the account that
holds the vault, because `op` otherwise asks which of your accounts to use:

```sh
op read --account "<your 1Password account>" "op://Development/taktus-connect-key-connected-reference/password" | ssh "<host that runs kubectl>" "kubectl --namespace <control-plane namespace> create secret generic taktus-connect-connected-reference --from-file=key=/dev/stdin"
```

Done by the owner on 2026-11-03: the Secret `taktus-connect-connected-reference` exists in the
control plane's namespace. Then tell the session in the issue. It adds the worker to the instance's configuration and asks
you to apply the private values in the same way as an install.

**Step 3 — the worker.** The session starts the reference worker with `TAKTUS_CONNECT_KEY_FILE`
pointing at a file it writes from the vault (`op inject`), connected to the instance's address.
The key never leaves the vault, that file and the instance's secret store.

**Rotation:** a new value in the vault item, then step 2 again with the Secret replaced, at once when it may have been seen.

## 5. What it must never be

- **Never the instance's administration key** or any other credential: a connected worker's key
  admits that worker and nothing else.
- **Never in this repository**, a chat, an issue or an environment variable a process listing
  shows.

## 6. What happens next

Write in the issue: **"NEED-0037 is provided."** The next session records it first, starts the
reference worker connected outbound, runs the instance's conformance suite for it, and reports
the record that names `binding: outbound`.

## 7. How to confirm

`taktusctl conformance list` on the instance shows the worker `connected-reference` with a
record whose configuration names `binding: outbound`.
