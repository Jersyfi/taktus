# ADR-0187 — A secret store the operator chooses fills the files Taktus reads

**Status:** accepted · extends the secret rule of CLAUDE.md §9 (a value read from the file
`TAKTUS_<KEY>_FILE` names) and `CREDENTIALS.md` · serves principle 13 · DEC-0224, NEED-0041 ·
issue #660

## Context

Every secret of an instance reaches it as a file. The control plane reads the file a variable
`TAKTUS_<KEY>_FILE` names; a connector and a worker read the file
`TAKTUS_CREDENTIAL_<NAME>_FILE` names, at the moment of a call. On one server the operator
writes those files by hand under `deploy/docker/secrets/`. On a cluster the operator creates the
Secrets the chart mounts. A rotation is a person writing a file again.

Since DEC-0224 the project keeps its secrets in a password manager, and NEED-0041 gives its
instance a read-only account there. An operator of another tenant keeps theirs in another
store, or in none. Principle 13 forbids depending on one.

Two places could read the store. **At run time**, through an adapter: every read of a secret
becomes a call of the store, behind a port of its own. **Before run time**, outside Taktus: a
program reads the store and writes the files Taktus already reads.

## Decision

### 1. The store fills the files; Taktus reads only files

Taktus keeps reading secrets from files and nothing else. No port for secret stores is added,
and no component knows that a store exists. A store is reached before Taktus reads, by a program
that writes the files.

### 2. One server: `deploy/docker/secret_store.py`

The program reads the operator's `deploy/docker/secret-store.json`. It names a command that
prints one secret for a reference — the store's own command-line tool — and, per file under
`deploy/docker/secrets/`, the reference of the value in the store:

```json
{"command": ["store-cli", "read", "{reference}"],
 "secrets": [{"file": "payments_token", "reference": "vault/payments/token"}]}
```

The command is run without a shell, with `{reference}` replaced in its arguments. Its output,
without the final line break, is the value. A file is written only when the value changed, in
place, so that a container whose compose secret is that file sees the new value without a
restart. A command that fails or prints nothing leaves the file as it is and is reported by the
file's name; the value is never printed. `--interval` repeats the pass, so that a rotation in
the store reaches the files without a person; `make up` runs one pass before starting when the
file exists. The program is standard library only, as `make up` needs only `python3`.

### 3. A cluster: the Secrets the chart names

On a cluster the chart mounts Secrets as files already, and the kubelet replaces a mounted
Secret's files when the Secret changes (the chart mounts none by `subPath`, which would not be
replaced). Filling those Secrets from a store is the cluster's own concern: an operator that
syncs a store into Secrets, or the program of §2 writing files from which the operator's
pipeline applies the Secret. The chart does not change. `deploy/k8s/README.md` says so.

### 4. Removing the store breaks nothing

Without `secret-store.json` the program does nothing, and the files are what the operator wrote.
With the store unreachable, every file keeps its last value. The removal test of §6 holds: the
store changes how a value arrives, not what reads it.

## Alternatives

**A secret-store port read at run time.** It would put a network call before every credential
read, make the store a dependency of every step, and need an adapter per store in the core. Its
one advantage, no copy on disk, is not one here: the files exist on that disk already, under the
same protection.

**A product's own operator or agent as the only way.** It would tie the product to one store or
one cluster tool (principle 13). It stays the operator's choice under §3.

## Consequences

- `deploy/docker/secret_store.py`, `deploy/docker/secret-store.example.json`,
  `tests/deploy/test_secret_store.py`, and one step in `make up` and `make start`.
- `CREDENTIALS.md` says that each parameter's file may be filled from a store.

## Where this promise ends

A value that Taktus reads once at start — the database's address, for one — takes effect only
at the next start; the connectors and workers read theirs at each call. A rotation reaches a file
within one interval of the program, not at once, and only while the program runs. The program
trusts the command the operator names: what it prints is the value, and a command that prints
the wrong value writes a wrong file. A value whose last line ends without a break and one that
ends with one are written the same. Writing a file in place can be read half written by a call
at that moment; the call then fails as unauthenticated and is retried by the step as any other.
The project's own instance runs on a cluster, so its rotation rests on §3; wiring its store
there is the owner's act under NEED-0041 and is not part of this decision.
