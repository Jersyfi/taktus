# DEC-0008 — The execution frame names allowed hosts, not forbidden ones

**Category:** DEFECT
**Raised in:** [#9](https://github.com/Jersyfi/taktus/pull/9), which adds the daemon and its roles
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

When Taktus hands a piece of work to a worker — a program that executes on its behalf — it
sends a *frame*: the ceiling of what the worker may do. The frame lists the tools the worker may
use. It also said what the worker may not do over the network, and it said it as a negation: a
list of forbidden patterns, with the example "no outbound network access" written as a pattern
that matches everything.

The contract's own principle is least privilege: a worker receives exactly what its work needs
and nothing more. A negation cannot express that. "Everything but this" grants whatever nobody
thought to forbid, and a worker that receives no forbidden list at all has been granted
everything. The affirmative form says the same thing the other way round: the frame names the
hosts the worker may reach, and everything else is refused. An empty list then means no outbound
access — the right default for most work — and a worker that needs a host has to be given it.

This is not only tidiness. The platform Taktus will run on enforces outbound network access
through a proxy that admits a list of hosts per job. Without a field that names allowed hosts,
Taktus has nothing to give that proxy, and the contract would say one thing while the platform
enforces another.

## 2. Why you are being asked

You are not. No row of `anchors.md` §1 applies: the worker contract is not released, no third
party relies on it (row O10 concerns released contracts), and nothing public changes. The
contract's text contradicted its own stated principle — least privilege expressed as a
negation — which is a documentation defect, row D6 of §2. Correcting it changes what the
software does — the field a worker receives — so the exception of D6 was tested: the change
follows from a principle the contract already states and adds no new one, and the contract is
unreleased. It is corrected and recorded here.

## 3. What you must decide

Nothing. The record exists so that the affirmative form is understood as the rule for every
restriction in a frame, not as a one-off rename.

## 4. What you need to know to decide

- **Frame.** The part of an assignment that bounds a worker: the autonomy level, the tools it may
  use, the hosts it may reach, how many steps it may take, and a deadline.
- **Least privilege.** Grant what the work needs, refuse the rest. The rest must not need
  listing, because nobody can list it completely.
- **Refused, not ignored.** A worker that receives something outside its frame must say so in
  its event stream and not do it. This already held for tools (check W-07). It now holds for
  hosts (check W-13): a worker that reaches a host outside the list, or treats an absent list
  as permission, fails conformance.
- **Why this is a defect and not a decision.** The contract stated the principle and then
  wrote a field that could not honour it. The correction makes the field match the principle;
  it does not choose a new principle.

## 5. Options

None for the owner. What the session did: `frame.forbidden` is gone; `frame.allowed_hosts` is
an explicit list of host names, absent or empty meaning no outbound access; a tool call that
reaches a host names it in the `tool.called` event, and a host outside the list is refused
there; the conformance suite gained check W-13 with a must-fail fixture, the reference worker
a fault that violates exactly that check, and the suite's meta-test proves the suite catches
it. Every example, the Python binding, the reference worker and the run component follow.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object to the correction: "Reopen DEC-0008" in an issue, with the reading
you hold.

## Outcome

**Corrected:** 2026-09-17
**What was wrong:** `contracts/worker/v1` expressed network restriction as
`frame.forbidden: ["net.egress:*"]`, a negation, while the contract's own text demanded least
privilege — an affirmative grant of exactly what the work needs.
**Why it was wrong:** a forbidden list grants whatever it does not name, and an absent list
grants everything; neither can express least privilege. It also gave the execution
environment's per-job host list nothing to be built from.
**What it now says:** `Worker.json` — `Frame.allowed_hosts`, an explicit list of hosts, empty
by default; `ToolCalled.host`; the README's §3 and §4; check W-13 in §7 and in
`CONFORMANCE.md`; the examples; `src/taktus/ports/worker.py`,
`src/taktus/components/run/domain/model/work.py` (`allowed_hosts` on worker work);
`src/taktus/conformance/rules.py` and `suite.py` (the stream rule, the `narrowed-hosts` run,
`--hosts`); `workers/script/worker.py` (hosts declared by the task, held against the frame, the
W-13 fault).
**What changed in substance:** the shape of the frame a worker receives: one field replaced by
its affirmative form. No released contract changed; the worker contract is unreleased.
**Recorded in:** [#9](https://github.com/Jersyfi/taktus/pull/9)
