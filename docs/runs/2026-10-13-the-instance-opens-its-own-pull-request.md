# 2026-10-13 — The instance opens its own pull request

The installed instance ran P-03 for real from 2026-10-12 18:25 UTC to 2026-10-13 00:06 UTC. It
ended with pull request #373, closing #278, authored by Taktus's own app: the last check of #66.
The same evening the instance ran P-01 and S-01 for real for the first time, which measures rows 3
and 4 of *What the next live run must measure* (`README.md`, issue #75).

## What ran

| | |
|---|---|
| Instance | the installed instance (#66), one node of 4 cores and 7.5 GiB, `v0.2.0-rc.8` to `rc.11` |
| Process | P-03 Implementation, version 6, at its declared level 4; P-01 version 3; S-01 |
| Connector | the repository connector as Taktus's own app (ADR-0033) |
| Worker | the coding worker in a cluster unit (`execution.kind: cluster`), its agent's model Haiku (DEC-0019) |
| Started by | the label `ready` (P-03 on #283, then 35 issues at once), and `taktusctl submit` as `idn_owner` with the owner's permission for runs of P-01 to P-03 on the instance |

## The result

**#373, opened by the app, the pipeline green.** Run `run_fd221e54dff23b6ad891` for #278: the
coding step used USD 1.26 and 136 quota units in all; it halted once at `create-branch` (finding 4)
and continued at its boundary on `rc.11`. The run before it, `run_0fe0ff759342c538f0fd` for #256,
implemented its issue for USD 0.69 and failed at the branch (finding 3). Four findings stood
between the first claim and the pull request. Each was fixed in a pull request of its own and
reached the instance in a release candidate the same night.

## The findings

1. **The proxy's 407 named no scheme** (#356). git asks a proxy without credentials first and
   sends the token from the proxy address only once a 407 names a scheme. Every clone failed
   with "CONNECT tunnel failed, response 407". Fixed in `rc.9`.
2. **Thirty-five runs at once, twelve without room** (#358). Forty-six issues labelled `ready`
   within a minute started thirty-five P-03 runs; `capacity.available` observed the platform once
   per event, before any run held memory. Twelve units could not be placed ("Insufficient
   memory") and their runs escalated. A unit without room now makes its step wait, and a pass
   starts one run under the condition. Fixed in `rc.9`. The runs that failed left the issues
   claimed by the app; releasing the claims is the owner's.
3. **A workflow file in the change** (#366). The coding agent changed a comment in
   `.github/workflows/ci.yml`; the app holds no right to change workflows, and the service refused
   the whole tree. P-03 now asks its worker to leave those files to a person, and the refusal
   names them. Fixed in `rc.10`.
4. **A branch write reserved by another operation's error** (#370). `create-branch` estimated 64
   quota units and had used 14 before; it was reserved 192, three times over, because another read
   through the same connector had used three units against one. The run halted one unit short.
   A bound is now calibrated by its own step. Fixed in `rc.11`.

Two more are open. The worker's workspace has none of the repository's tools (`make`, `uv`,
`pytest`): it could not run the checks its acceptance names, said so in the summary, and the
pipeline judged the change instead. The pull request's description repeats sections (#282).

## The measurements

### Row 3 — admission against real free capacity

**Not measured as the row states it, for a reason of the design.** `taktusctl capacity` on the
instance reported "memory: 642.2 MiB free of 768.0 MiB" and "cpu: 3.8 of 4 cores idle": the
memory is the control plane pod's own limit, not the node's 7.5 GiB, because the platform port
observes the process it runs in (ADR-0031, *Where this promise ends*). The deployment identity
may not read the node, so the node's own figures are those of #244. No `capacity.*` entry is in
the ledger: admission against that observation never refused a step. In a cluster the node's
scheduler is what admits a unit: it places a unit only where its requested memory, all of its
limit (section 7 of `deploy/k8s/README.md`), is free. Twelve units were not placed on 2026-10-12;
since #358 their steps wait for room instead of failing.

### Row 4 — the rehearsal

**Not yet measured.** S-01 for `connector.channel.repo` (`run_4cc450d0ad9757d28eea`) ended
`changed` and rehearsed nothing: P-01 and P-02 write a comment, and
`repository.comments.create` had never been called for real on the instance, so no recording
exists. P-03 is never rehearsed: its worker reaches hosts (ADR-0030). The first real P-01 run
(`run_8dcdc6951ec07a05f99c`) halted before its comment: its quota of 40 units is the whole
reserve of its uncalibrated `read-issues` (DEC-0192, #363). Once P-01 writes its report, S-01
answers from that recording.

## What it cost

USD 1.95 for the two coding steps, both within P-03's limit of USD 5 per run. The thirty-five runs
of finding 2 failed before their coding step.
