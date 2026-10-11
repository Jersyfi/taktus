# ADR-0088 — An unknown sender's contribution starts the triage for its owner, and a process holds its own steps

**Status:** accepted · makes UC-1.9 buildable (issue #245); amends what ADR-0040 §5 and
ADR-0048 §1 say of an unknown sender's event for one case, and adds to ADR-0042

## Context
UC-1.9 asks that an issue or a pull request opened on a public channel by a person Taktus does
not know starts a triage process of the organisation's own. The process acts for its owner,
and the person is its data, never its actor. It classifies the contribution as a defect, a
feature with its version, or spam. It asks the owner's approval for a defect or a feature,
keeps what is approved, closes what is declined with the reason, and closes spam without
asking. It never blocks a sender and never merges an outside pull request.

Four things it needs did not exist.

- **A way for such an event to start anything.** ADR-0040 §5 keeps an unknown sender's event
  nowhere: the sender is offered how to link the account, and that is all. ADR-0048 §1 makes an
  event out of a kept intake only, so the event never reaches a trigger. UC-4.14 says an
  unplaced sender starts no process a trigger names, and UC-1.9 keeps that rule.
- **A step that runs only for some results.** The run engine executes every step of a plan in
  order. A failed `check` fails the run. The triage has three outcomes that do different
  things: close as spam; keep in a version; close with the owner's reason.
- **A question the process asks itself.** An anchor is the tenant's configuration (ADR-0042
  §1). It selects a step by its tool actions, and the shipped default anchors nothing a
  repository does. UC-1.9 requires the owner's approval whatever a tenant configured.
- **A decline that the process acts on.** ADR-0042 §4 halts a run whose anchored act was
  declined. UC-1.9 requires that a declined contribution is closed with the owner's reason.

The repository connector, besides, could not close an issue and could not set a milestone.

## Decision

### 1. A channel's triage is configuration, and starts on a contribution only
`TAKTUS_TRIAGE` maps a channel to the process that triages it: `channel.repo=p05-triage`. A
channel named there is a **public channel** in the sense of UC-1.9: one anybody can write in.
Nothing else makes a channel public.

On such a channel, an accepted delivery whose sender the identity component cannot place, and
whose kind opens an item — `issue.opened` or `pull_request.opened` — is a **contribution**.
The intake keeps it as an intake event of status `contribution`, in the tenant the surface
receives for. It writes the outbox entry `intake.contribution`, naming the event, in the same
transaction. The kept event carries the channel, the kind, the context and the reply address.
It carries neither the sender's account nor their text: the account is written as `unknown`,
and the text is left out. The process reads the item from the system of record.

Everything else an unknown sender sends stays as ADR-0040 §5 says: answered with the offer,
kept nowhere. A contribution is offered the link as well; the offer is UC-1.7's and does not
change. A redelivery of a kept contribution writes nothing (ADR-0048 §4).

### 2. The automation role starts the triage for whoever activated it
The automation role reads `intake.contribution` beside `intake.accepted`, the oldest first, on
the same pass and only while it leads (ADR-0048 §3). For each entry it finds the active version
of the process the channel names. It places the identity that registered that version
(`activated_by`, ADR-0040 §6) and starts one run that acts for that identity, as a time trigger
does (ADR-0035 §6). The run's one input is the item's number. Its identifier is derived from
the tenant, the process and the event (ADR-0048 §4), so a second reaction to the same delivery
names the same run and starts nothing. The command records the event and the trigger kind
`contribution`, never the sender.

An entry waits — it stays unpublished — while no version of the process is active, or while
its registrant is not an identity the tenant knows. A process version registered after the
contribution arrived does not start for it.

Whether a run starts is a rule over the delivery, the identity component's answer and the
configuration. No probabilistic method decides it (UC-1.9 §2, ADR-0048 §2).

### 3. A step may run under a condition: `when`
A step's work may carry `when`: conditions in the shape of a `check` rule's, over the results of
the steps it depends on. Before anything of the step starts — before an anchor is asked — the
conditions are evaluated. When one does not hold, the step is **skipped**: it succeeds with the
result `{"skipped": true, "because": …}`, performs nothing, raises nothing and reserves nothing.
The ledger says `step.finished` with the outcome `skipped`, and the step's provenance record
names what the conditions read. A part a condition names that the result does not carry is
null, so a condition over it does not hold. Every reference in `when` must name a dependency,
checked before the run starts, as every `$from` is.

A skipped step's dependents run. A step that must not run after a skip says so in its own
`when`. This keeps the plan a fixed sequence of steps, each with its method, reason and
fallback, as ADR-0004 requires.

### 4. A step may ask before it acts: `ask`
A step's work may carry `ask`: a question, a situation and a proposal, as templates over
earlier results, and the role that decides, `owner` unless named. Before the step's act, at
every autonomy level, the run raises a decision request for it in the decision component, beside
the request of any anchor that names the act (ADR-0042 §3). The request has the anchor's two
options. Its class is `strategic`, and it names no anchor. The step waits in `waiting_human`,
and nothing of it starts until the request is applied. A rehearsal asks nothing (NTC-0079). A
question that names a value it does not carry is not raised: the step fails and the run
escalates.

An ask is the process's own anchor: the bundle declares it, and no tenant configuration removes
it. It can be added and never emptied, as ADR-0008 requires of anchors.

### 5. A process may act on a decline: `on_decline: continue`
By default a declined act halts the run, as ADR-0042 §4 says. A step whose `ask` says
`on_decline: continue` ends instead: it succeeds with the result
`{"declined": true, "by": …, "answer": …}`, where `answer` is the decider's answer as written,
words around the option included. The ledger says `step.decided` and `step.finished` with the
outcome `declined`. The act is not performed. The steps after it read the result through
`$from` and their own `when`. The decision port's verdict gains the answer as written for this.

### 6. The repository connector closes and places
Two operations, both `marked`:

- `repository.issues.close` comments why, then closes the item as not planned. The comment
  carries the mark. A repeat finds the comment and the item closed and does nothing. A pull
  request is closed through the issue interface, which cannot merge it.
- `repository.issues.milestone` puts an item in the open milestone of a given title. The
  milestone is its own mark, as a label is for `repository.labels.set`.

### 7. The rules `spam` and `classification`
`spam` searches a text for fixed patterns and says whether one matched; it is admissible for
`exact`. `classification` reads a judgement's answer — `class`, `version`, `summary` — and holds
it to the classes and the versions given; the screen's spam verdict wins. Its step carries the
judgement's class, never `exact`.

## Alternatives
- **An event trigger that matches unknown senders.** A filter on the sender would let any
  process start on any unknown sender's event, and UC-4.14 forbids it. The triage is one process
  per channel, named by the operator.
- **Keep the event as an ordinary intake and complete it into a command of the owner.** The
  intake would then hold a command whose sender is not its identity. The status `contribution`
  says what the event is, and nothing completes it into a command.
- **Branching steps, a step with two successors.** A graph with branches changes the plan's
  shape everywhere it is read: the diagram, the exactness statement, the takeover instructions.
  A condition on a step keeps the sequence and says per step when it acts.
- **Two processes, the second started by the first's label.** Taktus's own label is refused at
  the intake (it carries Taktus's account), and a second process would split one contribution's
  record over two runs.
- **An anchor the tenant must configure.** The approval would hold only where someone thought
  of it. UC-1.9 requires it everywhere.
- **Close a declined contribution by hand.** UC-1.9 §2 requires that the process closes it with
  the owner's reason.
- **A step of method `human` that returns the owner's answer.** `human` produces no result
  (ADR-0018) and has no executor; a decision request already carries the answer.

## Consequences
- `TAKTUS_TRIAGE` in `settings.py` and `.env.example`; the intake and the automation role read
  it. With it unset, nothing changes.
- The outbox topic `intake.contribution`; the intake status `contribution`.
- `work.when` and `work.ask` in a bundle (`examples/README.md`); two step transitions,
  `planned → succeeded` and `rejected → succeeded`, for a skipped step.
- `Verdict.answer` on the decision port.
- `repository.issues.close` and `repository.issues.milestone` in the reference connector and its
  fake service.
- The rules `spam` and `classification`.
- `blueprints/dev-orchestration/processes/P-05-triage.yaml`.

## Where this promise ends
- **Public is what the operator says.** A channel configured for triage is treated as public. A
  private channel configured so is triaged all the same.
- **Only an opened item is a contribution.** A comment, a label, an edit by an unknown sender is
  not triaged. An item opened while no instance received it is not triaged either: Taktus does
  not ask a tool what it missed (UC-4.14 §3).
- **The triage acts for whoever registered its version.** That identity must hold the role the
  ask names, or nobody can answer the request. Nothing checks this at registration.
- **A contribution is kept as data.** Its event stays in the intake table with status
  `contribution`, without the sender's account or text. It is deleted when the tenant's intake
  events are, which nothing does yet.
- **A skipped step looks like a succeeded one** to whatever counts succeeded steps. The ledger's
  outcome `skipped` and the result tell them apart.
- **The model's spam verdict closes without asking.** A wrong verdict closes a real contribution,
  which a person reopens. A text written to steer the model can make it answer anything the
  check admits: one of three classes and a planned version. It cannot make the process merge,
  block or act as anyone.
- **The versions are the roadmap's milestones.** A version that is already released is still
  one of them. Its milestone is closed, so `repository.issues.milestone` fails, and the run
  escalates to a person.
- **Blocking is not here.** No operation blocks a sender, and the process proposes nothing about
  one. A person blocks, in the host's own interface.
