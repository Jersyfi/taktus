# DEC-0179 — The session acts on the instance with the deployment identity

**Category:** NON-BLOCKING
**Mode entry:** M3.6
**Raised in:** the session of 2026-10-11 that takes up the milestones `0.1.0` to `0.3.0`; recorded in the pull request that records the owner's answers of that evening
**Issue:** none; the owner answered in conversation before a request was written, and this record is the question with the answer
**Needed by:** 2026-10-11
**Written after the answer:** the owner answered in conversation on 2026-10-11; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

Several tasks of the milestones need acts on the installed instance: an upgrade to a release that
carries the backup (#67, #251), a Job that configures the owner's channel (NEED-0020), the first
backup started at once, the checks of #66, #75 and #87. Until now every act on the cluster was the
owner's: the session's tool refused them, and the owner ran each command by hand. Working
unattended overnight is then impossible.

## 2. Why you are being asked

Putting a version into operation is the owner's (M3.6), and ADR-0013 D says a version is deployed
by a person or by another instance, never by Taktus itself. A session is neither Taktus nor the
owner; only the owner can let it act for him.

**Sources checked:** ADR-0013 D, ADR-0025 (the deployment identity is never given to Taktus),
M3.6 of both anchor pages, NEED-0007 (the deployment identity's rights: two namespaces, nothing of
the cluster as a whole), DEC-0174 (merging and the tag). None lets a session deploy.

## 3. What you must decide

May the session act on the instance with the deployment identity — upgrade it with the install
script, start and remove Jobs, read what runs?

## 4. What you need to know to decide

- The deployment identity reaches the control plane's and the execution namespace and nothing
  else: it creates no namespace and no object of the cluster as a whole, and it is never given to
  Taktus's own processes.
- The owner's workstation permits the session two kinds of command: the cluster's client with the
  deployment identity's configuration, and the install script.

## 5. Options

### Option A — yes, with the deployment identity alone (recommended)

- **Meaning:** the session upgrades the instance with the install script and runs Jobs in the
  control plane's namespace, with the deployment identity and nothing broader; every upgrade and
  every Job is named in the pull request or the record it belongs to.
- **Why recommended:** the identity's rights are already the boundary NEED-0007 drew; ADR-0013 D
  stays true — a person's permission puts the version into operation, not Taktus.

### Option B — no; every act on the cluster stays the owner's

## 6. What is blocked

The upgrade that switches the backup on and its first backup (#251), the last check of #66, #75 and #87.

## 7. How to answer

"DEC-0179: Option A.", "DEC-0179: Option B." or the owner's own wording.

## Outcome

**Decided:** 2026-10-11
**Answer:** Option A. The owner added to the workstation's permissions the cluster's client with the deployment identity's configuration and the install script, by a command the session gave on request.
**Reasoning given:** the owner's: the session is to work until the next evening without needing the owner.
**What it does not change:** root access to the machine stays the owner's alone; Taktus's own processes never receive the deployment identity (ADR-0025); a backup is restored onto the instance only on the owner's word ("never delete without asking", CLAUDE.md §9).
**Recorded in:** this pull request
