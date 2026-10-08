# ADR-0033 — Taktus authenticates to a repository service as an app of its own

**Status:** accepted

## Context
Until this decision the reference repository connector acted with one kind of credential: a
**personal token**. A personal token is a string a person creates in their account; whoever holds
it acts as that person, with that person's permissions, until it expires or is revoked. Every pull
request Taktus opened therefore appeared as the owner's (issue #50), and the token had to be
renewed by hand (NEED-0002, NEED-0006).

The owner delegated the question of how Taktus connects to its repository service, and the session
decided it on 2026-10-08 (DEC-0058): **an app of its own**. Most repository services offer such
apps. An **app** is an identity of its own on the service, not a person. It is installed on
chosen repositories with chosen permissions. It holds a **private key**, and with that key it can
obtain an **installation token**: a token that lives one hour and carries exactly the permissions
of the installation. The app for this tenant exists and is installed on two repositories
(NEED-0013).

The connector contract (ADR-0024, `contracts/connector/v1` §5) constrains how this can be built.
A connector acts with **the requesting identity's** credential, referenced by name in each call.
It has no credential of its own to fall back on: a call that references none is refused. Any
answer here must keep that.

## Decision

### 1. The app is the default; it is an identity, not a fallback
A tenant's instance reaches its repository service as an app of its own. The app is the
**requesting identity** of every call Taktus makes on its own behalf. It is bound to one
credential name, the one the connector declares for actions (`REPOSITORY_TOKEN` for the reference
connector). A call that references that name is served with an installation token. A call that
references no name, or another name whose value is absent, is refused exactly as before. The app
therefore changes who Taktus is on the service; it does not give the connector a credential to
use when the call names none. Conformance check C-03 holds in both modes, and the suite is run
against the reference connector in both (`tests/conformance/`).

### 2. A token is minted for use and never stored
To mint, the connector signs a short statement with the app's private key: "I am app N, until
time T", ten minutes at most. That statement is a **JWT** (JSON Web Token, RS256). The service
answers it with the app's installation on the repository, and then with an installation token.
The connector asks for the token **for its one repository**, whatever else the installation
covers. It holds the token in memory and nowhere else. It replaces the token **five minutes
before it expires**, so that no call starts with a token that may expire under it. It reads the
private key from its file at each minting and drops it after signing, so that a replaced key
takes effect at the next minting. Neither the key, nor a statement, nor a token is written to a
file, a result, an error or the log.

### 3. A refusal says why, and is never retried silently
A key the service does not accept, an app that is not installed on the repository, and a
suspended installation each end the call with cause `unauthenticated`, effect `none`, not
retryable, and a detail that names which of the three it was. A held token the service refuses
is dropped; the call ends `unauthenticated`, and the next call mints anew and gives the reason.
The operation itself is never repeated inside the call (CREDENTIALS.md, "When a credential
expires anyway").

### 4. Two parameters, read the one way
The app is selected by two parameters, both or neither:

- the app's **identifier**, configuration key `repository.app_id`, given inline as
  `TAKTUS_REPOSITORY_APP_ID`. It is not a secret: it names the app and grants nothing without the
  key. It is still kept out of public logs, because it identifies this tenant's app.
- the app's **private key**, credential `repository_app_key`, read from the file named by
  `TAKTUS_CREDENTIAL_REPOSITORY_APP_KEY_FILE` (DEC-0018).

One of the two without the other is a configuration fault, and the connector refuses to start.
Without both, the connector acts with the value under the referenced name, as before.

### 5. The personal-token mode stays, for a tenant without an app
A tenant may have no app: a service that offers none, or an owner who has not created one. The
connector then acts with the token the runtime puts under the referenced name. That mode is kept,
documented and tested; it is not the default. For this tenant the personal token of NEED-0006 is
retired once the instance acts as the app.

## Alternatives

- **A personal token as the default.** Rejected. Taktus would act as a person, which makes every
  act of Taktus look like that person's (issue #50). The token is long-lived, so a leak lasts. It
  must be renewed by hand, which is a need raised again and again.
- **A user authorisation** (a person signs in once, and Taktus acts as that person through a
  delegated token). Rejected. It removes the manual renewal and keeps the core problem: Taktus
  still acts as a person. Principle 14 forbids assessing a person; acting under a person's name
  attributes Taktus's work to them, which is the same confusion in the other direction.
- **The connector holds the app's token as a credential of its own, used for any call.**
  Rejected. It would break `contracts/connector/v1` §5: a call that references no credential
  would be served. Binding the app to one name keeps the contract unchanged.
- **Mint in the workflow with a third-party action, and hand the connector a token.** Rejected
  for the live test. It would test the token mode against the real service and leave the
  minting this decision introduces untested there. The live job hands the connector the key, and
  the connector mints as it does in production.

## Consequences

- What Taktus writes on the service appears under the app's name, as an automation.
- The connector makes two more requests when it mints — the installation, the exchange — and
  counts them as the consumption of the call that needed the token. Afterwards a held token costs
  nothing until it is replaced.
- The fake repository service speaks the app flow, so that the connector's tests and the
  conformance suite run in both modes without a network (`tests/fakes/repository_service.py`).
- The workflow `live` reads the app's identifier and key from the environment `live`, writes the
  key to a file outside its evidence for the length of the step, and fails when only half of the
  configuration is there (NEED-0016).
- `pyjwt[crypto]` becomes a direct dependency. It was already installed with the MCP library;
  only its declaration is new.

## Where this promise ends
The token is held in the connector's memory, so a person who can read that process's memory can
read the token for up to an hour. The key is read from a file at each minting, so whoever can read
the file can act as the app; the file's permissions are the operator's. Narrowing a token to one
repository narrows its reach, not its permissions within that repository: those are the
installation's, set where the app is installed. Conformance check C-04 looks for the values it is
handed; in the app mode it is handed the key, and it cannot know the tokens the connector minted.
The repository's own tests look for those tokens and statements, through the fake that issued
them; a third party's connector in the app mode has no such check. Whether a pull request opened
by an installed instance shows the app as its author is shown by the live test against the
scratch repository, not by a run of the instance, until the instance is installed (#66). How an
app is created — the manifest a session composes and the owner confirms — is not automated here;
the user interface's "connect" is `0.3.0`.
