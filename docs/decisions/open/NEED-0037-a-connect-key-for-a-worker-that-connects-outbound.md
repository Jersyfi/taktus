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

**Step 1 — the value.** On your machine, write a random value into a file only you can read:

```sh
umask 077 && openssl rand -hex 32 > "<path of the key file>"
```

**Step 2 — the instance.** Put the file into the instance's secret store as the connect key of
a worker named `connected-reference` (`CREDENTIALS.md`, row *Connect key of a connected
worker*); the session adds the worker to the instance's configuration and asks you to apply the
private values in the same way as an install.

**Step 3 — the worker.** The session starts the reference worker with
`TAKTUS_CONNECT_KEY_FILE` pointing at the same file, connected to the instance's address. The
file never leaves your machine and the instance's secret store.

**Rotation:** a new value into both places, at once when it may have been seen.

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
