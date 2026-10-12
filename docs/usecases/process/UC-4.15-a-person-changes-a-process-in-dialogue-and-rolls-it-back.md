---
id: UC-4.15
title: A person changes a process in dialogue, and rolls it back
component: process
epic: E4
serves: [P1, P2, P6, P10, P13]
state: specified
version: 0.3.0
tests: []
adrs: {ADR-0008: e6a4e033abd4, ADR-0011: f25413d512b9, ADR-0026: ccc4bd1f5423, ADR-0030: 9d551b889a39, ADR-0091: 92e6054cf4c8}
supersedes: null
---

# UC-4.15 — A person changes a process in dialogue, and rolls it back

## 1. What must be achieved

A person changes a process in their own words, from the web app or from the chat, and Taktus
works out the changed version with them. Nobody edits blocks or a file by hand to do it. The
person sees what would change before anything changes, and the change takes effect only when the
person commissions it. Every earlier version stays, and the person can make any of them current
again with one act.

## 2. How it is verified

- **A request becomes a proposal, not a version.** A person asks for a change to a process they
  may change. Taktus answers with a proposal: the changed process version, shown as its
  difference against the active version — every step added, removed or changed, and for each
  changed step its method kind, the reason for it, the methods not chosen and its exactness
  class. A test asks for a change and finds the active version, its triggers and its runs
  unchanged.
- **A proposal passes what a written version passes.** A proposal that would not register — a
  step without its method, reason or class, an `exact` step without a check, a level without its
  reason — is not offered as one. The person is told what is missing, in the same words the
  registration uses.
- **The proposal is rehearsed before it is commissioned.** The proposed version runs as a
  rehearsal in which nothing leaves the system (ADR-0030). The person sees what the rehearsal did,
  step by step, and what it would have sent out. A proposal whose rehearsal could not run says so
  and why.
- **Commissioning is the person's explicit act.** Only commissioning registers the proposal, as a
  new version that becomes the active one. The act is recorded in the ledger with the version and
  the identity that commissioned it. A free-text answer in the chat is read back and confirmed
  before it counts (ADR-0008). A proposal changed after it was rehearsed is rehearsed again before
  it can be commissioned.
- **What registration guards stays guarded.** A proposal that raises the autonomy level needs the
  approval that registration asks for any raise (ADR-0026). Commissioning skips no check a
  version written by hand passes.
- **Rolling back is one act.** A person names an earlier version, and its content becomes current
  again as a new version. The version it replaces stays registered and unchanged. A run under way
  finishes on the version it started on. Nothing is deleted.
- **The same from the web app and from the chat.** The same request gives the same kind of
  proposal in either. A proposal made in one can be commissioned or discarded in the other. A
  rollback made in one is visible in the other.
- **Only who may.** A request, a commissioning and a rollback are taken only from an identity the
  tenant knows and that may register versions of the process. Anyone else is answered as for a
  process that does not exist.

## 3. Where the boundary lies

**Not a visual builder.** No block is dragged and no graph is drawn by hand; the picture of a
process shows and explains it (UC-4.2, UC-6.10). **Not a change Taktus makes on its own.** That
is UC-4.3, within the frame a process's owner set. **Not a new process from nothing.** That is
UC-4.1, which this use case shares its rehearsal and commissioning with. **Not the bundle format
itself**, which is ADR-0011's. **Not rights per role.** Who may change which process is UC-7.3;
until it exists, whoever may register a version by hand may change it here. **Not a merge of two
proposals.** Two proposals for the same process are two proposals; commissioning one leaves the
other to be made again against the new version.

## 4. What it rests on

The process version and its registration (`docs/architecture/control-plane.md` §4); the
rehearsal (ADR-0030); the reading of a free-text answer (ADR-0008); the autonomy statement
(ADR-0026); the plan and its commissioning (UC-1.2); the process from a description (UC-4.1);
Taktus's own changes and their rollback (UC-4.3), whose rollback rule this use case shares; the
owner-facing channel (UC-6.11) and the web app (UC-6.10). The roadmap's `0.3.0` names *pair
editing with rollback*, and it is complete when *a process can be created, viewed, changed and
rolled back entirely from the web app and chat*. The blueprint UC-01 asks the web app for pair
editing (`AF-01-dev-orchestration.md`). Not written as a use case before: put to the owner in
DEC-0186, and in force on its provisional answer, Option A. ADR-0091 says how it is built.
