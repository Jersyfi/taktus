# NEED-0013 — An app of its own on the repository service

**Kind:** account
**Raised in:** [#97](https://github.com/Jersyfi/taktus/pull/97)
**Issue:** [#98](https://github.com/Jersyfi/taktus/issues/98)
**Needed by:** 2026-10-20
**Foreseeable since:** [#97](https://github.com/Jersyfi/taktus/pull/97), where the session decided, on the owner's delegation, that Taktus connects to the repository service as an app of its own (DEC-0058)

## 1. What is needed

An **app on the repository service that is Taktus's own**, created under your account, and
installed on this repository and on the scratch repository of the connector's live test. Taktus
then acts under the app's own name, with exactly the permissions the app is installed with, and
with tokens that live one hour and are minted for each use from the app's private key. The app's
webhook delivers the repository's events to the deployed instance.

## 2. Why

Today Taktus acts with a personal token of your account (NEED-0002, NEED-0006): every pull request
Taktus opens appears as yours (issue #50), and the token is long-lived and personal. An app is not
a person, does not expire into a renewal, and is created the same way for every tenant
(DEC-0058). The scratch repository becomes one more installation, so the live test needs no token
of its own (NEED-0011, superseded).

## 3. By when

**2026-10-20**, with the install of the deployment, so that the instance acts under the app from
its first run and its webhook is switched on with the install.

If it is not there by then: the instance acts with NEED-0006's personal token, under your name,
and receives no events; the backlog task that moves the connector to the app waits.

## 4. How to provide it

The app is created through the service's **app-manifest flow**: the session composes the app's
description — name, permissions, events, the webhook's address switched off until the install —
and you confirm it with one click. Nothing is typed by hand, and no value passes through you or
the session's output.

1. **Tell the session you are ready.** It starts a small page on your workstation
   (`http://localhost:8765/`) that sends the composed description to the service.
2. **Open that page** in the browser in which you are signed in to the service, and press
   **Create** on the service's page that follows. The service sends you back to the local page,
   which receives a one-time code and exchanges it at once for the app's identifier, its private
   key and its webhook secret, written into files readable by you alone. The page then shows the
   app's install link.
3. **Install the app** with that link on exactly two repositories: this one, and the scratch
   repository the session creates for the live test. Not on all repositories.

The permissions the description asks for, and no others: contents, issues and pull requests read
and write; metadata read; checks, actions and commit statuses read. The events: issues, issue
comments, pull requests, check runs, workflow runs. The webhook is created **inactive**: it is
switched on at the install, when the instance can receive it, with NEED-0010's secret.

## 5. What it must never be

- **Never installed on all repositories** of the account: two, named above.
- **Never given more permissions** than section 4 lists. A missing permission is a change to
  this record first and to the app second.
- **The private key never pasted into a chat, a session, an issue or a pull request**, never
  committed. It goes into the file the exchange writes, and into a secret in the control plane's
  namespace, and nowhere else.
- **Never the personal token's replacement by hand**: NEED-0006's token is retired once the
  connector acts as the app, under the backlog task that moves it.

## 6. What happens next

Tell the session: **"NEED-0013: ready."** It starts the page; you click and install; the session
confirms with section 7 and records the outcome. The backlog task that moves the connector to the
app follows.

## 7. How to confirm

Without revealing anything: the app's page on the service lists the two installations and the
permissions of section 4; and a token minted from the private key lists exactly the two
repositories — the session checks that and prints only the repository names.

## Outcome

**Provided:** 2026-10-08
**Confirmed by:** section 7, run by the session on 2026-10-08. The app has one installation, on
selected repositories, with exactly the permissions and events of section 4; a token minted from
the private key reaches exactly this repository and the scratch repository, and expires after an
hour. Only repository names, permissions and events were printed.
**How it was provided:** through the app-manifest flow, as section 4 describes: a page on the
owner's workstation sent the composed description to the service, the owner pressed Create and
installed the app on the two repositories, and the page exchanged the one-time code for the
app's private key straight into a file readable by the owner alone. The name the description
proposed was taken on the service; the owner chose the one the session gave instead. The session
set the app's webhook secret to NEED-0010's, the webhook stays inactive until the install, and
the app's identifier and key are also a secret in the control plane's namespace. The scratch
repository was created by the session, private. The app's name, identifier and the secret's name
are in the owner's private note. Moving the connector to the app, and retiring NEED-0006's token,
is #99.
**Recorded in:** [#97](https://github.com/Jersyfi/taktus/pull/97)
