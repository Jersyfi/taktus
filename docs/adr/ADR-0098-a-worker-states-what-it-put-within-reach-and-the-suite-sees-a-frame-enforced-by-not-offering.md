# ADR-0098 — A worker states what it put within reach, and the suite sees a frame enforced by not offering

**Status:** accepted · adds to ADR-0007 · worker contract v1, additive

## Context
Checks W-07 and W-13 of the worker contract prove that a worker keeps to its frame. The frame
names the tools a worker may use (`allowed_tools`) and the hosts it may reach
(`allowed_hosts`). The suite runs the worker's work once with everything allowed. Then it takes
out one tool the work used and runs it again, and does the same with one host. It expects to see
the worker refuse what was taken out: a `tool.called` event with `refused: true`. When the
second run never attempts it, the suite reports the check *inconclusive*: it saw no breach, and
it saw no refusal either.

Until #425 the coding worker offered its agent every tool it maps and refused a call outside the
frame when the agent made it. A refusal ends the assignment. Three runs on the installed
instance ended so, on a web fetch the agent was offered and not allowed (#424). Since #425 the
worker offers its agent only the tools the frame allows, and no fetch where no host may be
reached. The runs keep going, and they cost less.

The suite then lost sight of the frame. Run against the real agent on the instance on
2026-10-15, the narrowed runs never called the fetch, because the agent was never offered it.
W-07 and W-13 ended *inconclusive*, and the whole run *incomplete*. An adapter's maturity
counts only its last conformance run, so the coding worker read *experimental*. A process at
autonomy level 3 or above uses only adapters at *verified* or above, and P-03, at level 4, was
refused.

A frame kept by not offering is stricter than one kept by refusing: nothing outside it can even
be tried. The suite had no way to see it. A worker could not say what it offered, and the suite
reads only what a worker says.

## Decision

### 1. The event `reach.stated`
The worker contract v1 gains one event type, `reach.stated`. A worker emits it at most once per
assignment, before the first `step.started`. It carries two fields:

- `tools`, required: every capability a call of this assignment can be made under, refused or
  not. A capability left out cannot be called at all.
- `hosts`, optional: every host a call of this assignment can name. A host left out cannot be
  reached at all. Without the field, the worker bounds the hosts only at the moment of a call.

The statement is optional. A worker that offers its work every tool and refuses at the call
states nothing, and the contract asks nothing more of it. A rejected assignment carries no
statement, since its stream is one event.

### 2. What the stream rules hold a statement to
A statement is held to the calls of its own stream. A `tool.called` under a capability the
statement leaves out fails W-07, refused or not: the statement said no such call could be
made. A `tool.called` that names a host the statement's `hosts` leave out fails W-13 the same
way. A second statement, or one after the first step, fails W-07. W-07 owns the event's shape
as well.

### 3. What the suite reads from it
In the narrowed run of W-07, a worker that never attempted the withdrawn tool passes when its
statement leaves that tool out. In the narrowed run of W-13, a worker that never named the
withdrawn host passes when its statement names hosts and leaves that one out. A worker that
states nothing and never attempts stays *inconclusive*, as before. A call outside the frame
that is not refused fails, as before, with or without a statement.

### 4. The coding worker states its reach
The coding worker (`workers/claudecode/`) emits the statement at the start of every
assignment, from the same list it offers its agent. `tools` is that list in the contract's
terms: the capabilities of the agent's tools, `code.test` beside `shell.sandboxed` where the
frame allows it, and `web.fetch` where the task names hosts that the worker holds against the
frame itself. `hosts` is stated only where no fetch is offered. Then the hosts the task names
are the only ones a call can name. With a fetch offered, the agent may name any host, and the
worker holds each at the moment of the call.

The second coding worker (`workers/codex/`) states nothing. It offers its agent no list of
tools; its agent can always attempt a command, and the worker refuses an item outside the frame
when it appears. Its refusal stays observable, so the checks see it as before. The reference
worker and the training worker run no agent and call every tool themselves; they refuse at the
call and state nothing either.

The fake agent the gate runs the coding worker against now behaves as the real one: it never
calls a tool it was not offered. A tool it was offered and not approved it calls, and is denied.

## Alternatives
- **Revert #425.** The suite would see refusals again, and the runs would end on them again.
  That costs real money for a check's sake.
- **A narrowed run that the worker cannot avoid attempting.** The suite would have to make an
  agent call a tool it was not offered. An agent that is not offered a tool cannot call it. That
  is the property worth keeping.
- **Accept *inconclusive* as a pass for W-07 and W-13.** Every worker that never attempts the
  withdrawn tool would then pass, including one that simply did not need it this time. The
  statement is what separates the two.
- **A field on the answer to `POST /v1/assignments`.** The state answers three endpoints and
  changes as the assignment runs; a statement about one assignment's reach belongs in the
  assignment's record, the stream, where the stream rules can hold the calls against it.
- **A field on `capabilities`.** What a worker offers depends on the frame of each assignment,
  not on the worker alone.

## Consequences
- `Worker.json` gains `ReachStated`, one more member of `Event`; the port
  (`src/taktus/ports/worker.py`) binds it. The run reads the event and acts on nothing in it.
- `rules.py` holds a statement to its stream (`reach_violations`) and answers the suite whether
  it leaves a tool or a host out (`not_offered`).
- Fixtures: one valid transcript with a statement, three invalid ones (two for W-07, one for
  W-13), and the event's own examples.
- The coding worker's fault W-13 now also offers the fetch where no host is allowed, so that it
  is caught where the agent reaches its host itself.
- A worker built against v1 before this change keeps passing: it states nothing, and nothing it
  did is judged differently. A control plane built before it does not know the event, and fails
  the stream of a worker that sends one. An instance therefore takes the control plane of a
  release with or before that release's coding worker image. Both sides ship from this
  repository, and no release of Taktus is out yet, only candidates, so v1 may still move
  (anchors.taktus.md, M3.5). `assignment.finished` gained `limit` the same way (W-14).

## Where this promise ends
The suite believes a statement it cannot contradict. A worker that leaves a tool out of its
statement and offers it anyway passes W-07 whenever the tool is not called in the narrowed run.
Nothing the suite can read from the worker's endpoints tells that apart from a worker that
told the truth; a false statement is caught only by a call the stream shows. Whoever relies on
the pass relies on the worker's own account of what it offered, and on the worker's code.

The coding worker's statement is as true as the agent's own tool list. It states what it passes
the agent in `--tools`. Should the agent ever offer a tool beyond that list, a call to it would
fail W-07 against the statement, and the run would end on the refusal as before #425.

`hosts` bounds only the hosts a call names. What a shell command reaches over the network is
named by no call; the execution environment's allowlist is the wall there, as it was before
(ADR-0089). A statement with `hosts: []` therefore says that no call names a host, not that no
packet leaves the unit.
