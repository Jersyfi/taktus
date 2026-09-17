# DEC-0009 — The credential register lists parameters, not deployment names

**Category:** DEFECT
**Raised in:** [#9](https://github.com/Jersyfi/taktus/pull/9), which adds the daemon and its roles
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

The repository keeps a register of the secrets the software needs: `CREDENTIALS.md`. Since the
first commit its rule has been "names, never values": a secret's value never enters the
repository, and the register lists the secret by its name, what it is for, where it is used and
how to rotate it.

A second rule holds as well: the repository is public, and the name a secret has in a particular
deployment — the path in a secret store, the key in a vault, the variable a container reads —
belongs to whoever operates that deployment, not to a public document. The two rules looked as
if they contradicted each other. They do not. A *name* in the first rule meant "not the value";
it never had to mean "the name my deployment uses". What the software actually needs is a
*parameter*: a thing described by its purpose, which an operator maps to a concrete secret in
their own configuration. A parameter also survives a move between environments; a deployment's
name does not.

The register described its rows as names. One of them, the database connection, was named by
the environment variable a specific way of deploying happens to use; the others by the reference
names the connector contract carries, which are parameters already. The register's own
description of what it holds was the defect.

## 2. Why you are being asked

You are not. No row of `anchors.md` §1 applies: no secret changes, nothing public changes but the
wording of a document that was already public. Two statements of the repository's own rules
looked contradictory, which is row D6 of §2, and is corrected and recorded here.

## 3. What you must decide

Nothing. The record exists so that the next credential is added as a parameter, and so that
nobody writes a deployment's secret name into a public file because "names are allowed".

## 4. What you need to know to decide

- **Parameter.** What the software needs, described by its purpose: "the database connection",
  "the repository access token of the requesting identity". A parameter has permissions it
  needs, a rotation cadence, and a key or name through which it is supplied.
- **Configuration key.** The dotted key the configuration port reads (`database.url`). An
  operator supplies the value under it; how — a variable, a file, a secret store — is the
  configuration adapter's business and the operator's.
- **Reference name.** Where a contract carries the reference — a credential in an assignment
  or in a connector call — the name in the call is the parameter's name at that seam, and the
  runtime that starts the adapter makes the value available under it.
- **Why this is a defect and not a decision.** No secret, no permission and no rotation changes.
  Only what the register says it holds changes, to what it always should have held.

## 5. Options

None for the owner. What the session did: rewrote `CREDENTIALS.md` so that every row is a
parameter — purpose, permissions, rotation, and the configuration key or reference name it is
supplied through — and stated both rules and how they fit; aligned the four places that
described the register as a list of names (`CLAUDE.md` §9, `README.md`, the connector contract's
§3, the reference connector's README).

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object to the correction: "Reopen DEC-0009" in an issue, with the reading
you hold.

## Outcome

**Corrected:** 2026-09-17
**What was wrong:** `CREDENTIALS.md` described itself as a register of secret *names* and named
the database connection by one deployment's environment variable, while the repository is
public and a deployment's secret names belong in the operator's private configuration.
**Why it was wrong:** "names, never values" was read as "the deployment's names"; what the
register needs to hold is the parameter — purpose, permissions, rotation, how it is supplied —
which survives a move between environments, and which a deployment's name does not.
**What it now says:** `CREDENTIALS.md` — one row per parameter with purpose, the permissions it
needs, its rotation and the configuration key or reference name it is supplied through; both
rules stated and reconciled. `CLAUDE.md` §9, `README.md` (*Operating it*),
`contracts/connector/v1/README.md` §3 and `src/taktus/adapters/driven/connectors/github/README.md`
refer to the register as describing parameters.
**What changed in substance:** nothing the software reads. The configuration key and the
reference names are unchanged.
**Recorded in:** [#9](https://github.com/Jersyfi/taktus/pull/9)
