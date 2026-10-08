# DEC-0058 — Taktus reaches the repository service as an app of its own

**Category:** NON-BLOCKING
**Raised in:** the owner's answers of 2026-10-08, second round, to the session's questions on NEED-0008 to NEED-0012; recorded in [#97](https://github.com/Jersyfi/taktus/pull/97)
**Issue:** none; the owner answered in conversation, and delegated two of the questions to the session
**Needed by:** 2026-10-08
**Written after the answer:** the owner answered in conversation on 2026-10-08; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

Five needs of the deployment were still open. The owner answered three of them and gave two to
the session to decide: how the webhook secret is provided, and how Taktus connects to the
repository service in a way that lasts. Today Taktus acts on the repository with a personal token
of the owner's account, so every pull request it opens appears as the owner's (issue #50).

## 2. Why you are being asked

How a need is provided is the owner's act (M2.5); a limit — how long backups are kept, how often a
live test may run — is the owner's (M3.10); how Taktus authenticates to a service it depends on is
architecture, which the owner delegated here.

**Sources checked:** the vision (principle 4, tool-agnostic; principle 13, no lock-in; principle
14, no person assessed — and no person impersonated), the ADRs (ADR-0013 C on repair, ADR-0024 on
the connector, ADR-0025 on what an instance may hold), both anchor pages (M2.5, M3.2, M3.10) and the
register (DEC-0048, DEC-0057, NEED-0002, issue #50). None decides how a tenant's instance is
connected to its repository service.

## 3. What you must decide

How backups are kept, how often the live tests run, how the webhook secret is provided, and how
Taktus connects to the repository service.

## 4. What you need to know to decide

- **A personal token** acts as the person who made it, lives long, and is renewed by hand.
- **A user authorisation** (OAuth): a person signs in once and Taktus acts as that person.
- **An app of its own** on the repository service: installed on chosen repositories with chosen
  permissions; it acts under its own name; it mints a token that lives one hour for each use, from
  a private key it holds; and it carries its own webhook, signed with a secret of its own.
- **Object lock** makes a stored backup impossible to delete until its retention ends; without it,
  whoever holds the credential can delete.

## 5. Options

### Option A — as answered and decided (recommended)

- **Meaning:** see the outcome.
- **Consequence:** see the outcome.
- **Effort:** the needs as rewritten, the backlog issues named in the outcome.
- **Reversibility:** cheap, except that a backup deleted is deleted.
- **Why recommended:** the owner's answer and the owner's delegation, below.

### Option B — the proposals of the first round

- **Meaning:** object lock with 30 days; weekly live tests; a personal token for the scratch
  repository.
- **Consequence:** retention fixed outside Taktus; a second personal token to renew.
- **Effort:** as before.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing.

## 7. How to answer

"DEC-0058: Option A." or "DEC-0058: Option B."

## Outcome

**Decided:** 2026-10-08
**Answer:** the owner's, in conversation, and the session's where the owner delegated:
- **The public name (NEED-0008)** is chosen and its records exist. The name is in the owner's
  private note, not here. The session finishes the certificate. The wiki is left for `0.3.0` and
  not recorded here.
- **Backups (NEED-0009)** go to a bucket at the owner's object-storage provider, without object
  lock. **Taktus manages the retention itself, configurable, 30 days by default.** Backups are
  **not encrypted by default; encryption is an option Taktus offers.** Consequence, accepted with
  the answer: the credential may delete, so an instance that is compromised can delete its own
  backups; the retention Taktus applies is the only protection.
- **The webhook secret (NEED-0010)** — delegated. The session decided: it generates the secret
  itself, into a file readable by the owner alone and into a secret in the control plane's
  namespace; no person sees it. It becomes the webhook secret of the app below, set when the app
  is created.
- **The live test of the connector (NEED-0011)** — the proposal accepted, the frequency judged
  excessive. The session decided: **monthly and by dispatch** instead of weekly, for both live
  tests. The owner's preference, recorded as a requirement: **Taktus notices on its own when the
  interface to the repository service stops working, from its real calls, and reports it through
  the channel its instance has** — for this tenant, the chat channel.
- **How Taktus connects to the repository service** — delegated. The session decided: **an app of
  its own on the repository service**, not a personal token and not a user authorisation. It acts
  under its own name (issue #50), with exactly the permissions it is installed with, with tokens
  that live an hour and are never stored, and it brings its webhook with it. **It is created once
  through the service's app-manifest flow**: Taktus composes the app's description — name,
  permissions, events, webhook address — and the owner confirms it with one click; until Taktus
  has a user interface (`0.3.0`), a session composes it and the owner clicks, and afterwards the
  interface offers the same as "connect". A user authorisation was rejected because Taktus would
  act as a person, and a personal token because it is long-lived and personal. The scratch
  repository of the live test is one more installation of the same app, so NEED-0011's token is
  not needed.
- **NEED-0012:** the key exists locally; the session places it. What a cap per run means is
  explained to the owner before it is set.
**Reasoning given:** the owner's: Taktus should manage its backups and notice its own failures;
weekly is more testing than the interface needs. The session's: an app is the one way that is
not a person, does not expire into a renewal, and works the same for every tenant.
**Confirmed:** 2026-10-08, the owner: the session's decisions are accepted as proposed — the app
of its own, the webhook secret generated by the session, the live tests monthly, and the
connector's live test through the app (NEED-0011 superseded). For NEED-0012 the owner decided to
use the key already in the credential directory, and accepted a cap of USD 0.50 per run.
**Recorded in:** [#97](https://github.com/Jersyfi/taktus/pull/97): NEED-0008, NEED-0009 and
NEED-0010 provided; NEED-0011 superseded by NEED-0013, the app; `.github/workflows/live.yml`
monthly; backlog issues for the app, for retention and encryption of backups, and for noticing a
broken interface.
