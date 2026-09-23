# DEC-0022 — The endpoint worker isolates nothing, and the operator was not told

**Category:** DEFECT
**Raised in:** [#26](https://github.com/Jersyfi/taktus/pull/26), which corrects the defects the first live run met
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

A `worker` step's execution unit comes to exist in one of three ways (ADR-0002):
`process` starts a child process and isolates nothing, `container` starts a container with
limits and a network that reaches the allowed hosts and nothing else, `cluster` will start a
pod. A fourth way is not in that table: `endpoint`, a worker that is **already running**
somewhere, which the control plane simply calls.

The rule "an unisolated unit is refused from autonomy level 3 upwards" is enforced in the
execution port, and it is enforced on the adapters that *start* a unit. It cannot be enforced
on `endpoint`, because the control plane did not start that worker and cannot know what is
around it. The code says so where a reader of the code will find it
(`src/taktus/composition/settings.py`: "Its isolation is whoever runs it").

Nowhere else did. `.env.example` describes `endpoint` as "a worker that is already running, at
TAKTUS_WORKER (default)" and stops. ADR-0002's table does not list it. And
`tools/first_run.sh` — the command an owner runs — starts the coding worker as a plain process
on the machine, with the machine's whole network, and says nothing about it, while the process
it then runs, P-03 Implementation, declares autonomy level 4 with the reason "the worker runs
in isolation with exactly the hosts and credentials the frame names".

In the first live run of 2026-09-23 that reason was not true of the run. The worker's frame
named one allowed host, the repository's; the worker reached whatever the laptop could reach,
because nothing stood between them. Nothing came of it — the agent did what it was asked — and
the claim was still wrong, in a place where a wrong claim is worth correcting on its own.

## 2. Why you are being asked

You are not. The repository asserted an isolation that the configuration it ships in
`tools/first_run.sh` does not provide. Entry M1.4 of `docs/decisions/anchors.taktus.md` makes
the correction the session's, recorded here. Nothing is weakened: the correction is words, and
the words say less than before.

## 3. What you must decide

Nothing here. Whether the core should go further and **refuse** an endpoint worker from
autonomy level 3 upwards unless the operator asserts its isolation is a change to what the
software does at an autonomy boundary, and it is a proposal in an issue, not a correction.

## 4. What you need to know to decide

- The three isolation levels the execution port knows are `none`, `container` and `cluster`.
  `endpoint` is not one of them: it is the absence of a unit to isolate, because the unit
  already exists.
- `frame.allowed_hosts` (DEC-0008) is enforced by the `container` adapter, through a per-job
  egress container. With `process` it is not enforced, and with `endpoint` it is not enforced
  either. A process bundle that names allowed hosts and runs through `endpoint` names them
  for the record and for the day it runs in a container.
- `tools/first_run.sh` is a development command that starts everything on one machine. It is
  not, and does not claim to be, an operating deployment — but it also did not say which of
  P-03's guarantees hold when it is the thing running P-03.
- The gap is closed by configuration, not by code: `TAKTUS_EXECUTION=container` with the
  coding worker's own image gives the run exactly the isolation P-03's reason describes. The
  script does not offer that path today.

## 5. Options

None for the owner. What the session did: said plainly, in the three places an operator
looks, that `endpoint` carries whatever isolation the person who started the worker gave it,
and that `tools/first_run.sh` gives it none. `.env.example` says it beside the setting;
`tools/first_run.sh` says it in its header, where the reader is about to run it; ADR-0002's
*Where this promise ends* says that `endpoint` is outside its isolation table and why the
rule cannot reach it. P-03's autonomy reason now says which of its conditions depend on how
the worker is run.

**Not done here, on purpose:** refusing an endpoint worker at level 3 and above. It would be
the stronger answer, and it would stop `tools/first_run.sh` from running P-03 at all until the
script grew a container path — a change of what the software does at an autonomy boundary,
which is the owner's (M3.9 is about raising a level; this would tighten the condition under
which one may be claimed, and no entry covers it). It is raised as a proposal in an issue,
with what it would cost.

## 6. What is blocked

Nothing. The first live run happened through `endpoint`, and the run report says so where it
reports what the run proved and what it did not.

## 7. How to answer

Nothing to answer. To object to the correction: "Reopen DEC-0022" in an issue, with the
reading you hold.

## Outcome

**Corrected:** 2026-09-23
**What was wrong:** `.env.example`, `tools/first_run.sh` and ADR-0002 described the `endpoint`
execution kind without saying that it carries no isolation of its own, while P-03's autonomy
reason claims the worker "runs in isolation with exactly the hosts and credentials the frame
names" — and `tools/first_run.sh`, which runs P-03, starts the worker as a plain process with
the machine's whole network.
**Why it was wrong:** an isolation claim that the shipped command does not honour is the one
kind of documentation error that costs more than confusion. A reader who believes it runs a
level-4 process believing the frame is enforced, and it is not.
**What it now says:** `endpoint` means the isolation is whoever started the worker's; with
`tools/first_run.sh` that is nobody, and the script says so where it is read. ADR-0002 states
that its isolation rule reaches the adapters that start a unit and not a worker that is
already running. P-03's autonomy reason names the condition it depends on.
**What changed in substance:** nothing the software does. Three documents and one process
bundle's reason say what was already true.
**Recorded in:** [#26](https://github.com/Jersyfi/taktus/pull/26)
