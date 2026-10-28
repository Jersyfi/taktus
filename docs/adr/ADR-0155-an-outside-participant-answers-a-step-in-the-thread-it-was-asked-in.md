# ADR-0155 — An outside participant answers a step in the thread it was asked in

**Status:** accepted · extends ADR-0008 (the confirmation loop), ADR-0040 (who a sender is),
ADR-0042 (anchors) and ADR-0142 (outward messages) · issue #337, UC-1.12

## Context

A supplier confirms a delivery date. A client approves a quote. An authority answers an inquiry.
Each of them is a step of a process, and each answers in the channel they already use: a mail,
a chat. None of them has a Taktus account, and none should need one.

Four facts shape the decision.

- A sender Taktus cannot place is never an actor (ADR-0040). What they write is offered a link
  or dropped. It never becomes a command.
- A free-text answer is never acted on silently. Its reading is reflected back and confirmed
  first (ADR-0008).
- A message that leaves the system passes the frame of ADR-0142: labelled where a model wrote
  it, checked by a step of its own, held by rule.
- A `human` step had no executor. A run that held one was refused before it started.

## Decision

### 1. The question is an ordinary connector step

The process asks its question with a connector step of its own: `mail.messages.send`,
`chat.threads.post`, any delivery. That step is under ADR-0142 like every other outward
message: a model's draft is labelled and checked, a promise and mass sending wait for a person,
the delay and the quiet hours hold it. Nothing in this decision sends a question.

### 2. The answer is a `human` step addressed to a participant

The step after it has method `human` and names the participant in its work:

```yaml
participant: supplier                                   # a role outside the organisation
channel: channel.mail                                   # the channel the answer arrives in
thread: {$from: ask-supplier, $select: message_id}      # the conversation it is expected in
options: [confirmed, delayed]                           # optional: read by rule as one of them
```

`participant` is a role name, never a person and never an identity. `thread` is resolved from
the question's result when the step is reached. It is the token the channel's intake reports as
the conversation's thread (`context.thread`): the first message's `Message-ID` for mail, the
first post's timestamp for chat. A thread that does not resolve to a text fails the step.

The step then waits. Its block is `wait.external`, cause `awaiting_participant`, with the role:
the one who answers is outside the organisation. The
block keeps the channel and the thread. The step is `waiting_human`, recorded as `step.awaiting`
with outcome `participant`, and the run waits for a person, as it does for a confirmation.

### 3. The answer is matched by its thread, before identity

An intake from a person, with text they wrote, is offered to the participant's answers before
anything else of the owner-facing channel (`ChannelAnswers`). They match it when one waiting
step of the tenant expects an answer in the intake's channel and thread. The sender's identity
is not asked. A linked person and an unknown sender are treated alike. Nothing else they write
anywhere is taken.

The first account that answers is the participant's for the step. A later message from another
account in the same thread is not taken, and goes on as any other message.

### 4. The answer is reflected and confirmed (ADR-0008)

The answer is read by rule. Without `options` the reading is the text itself. With `options` it
is the one option the text names, as a whole word and case-blind. A text that names none, or
more than one, is not read. The participant is told the options and asked again.

A reading is said back in the same thread: what Taktus read, and "Reply yes to confirm, or
answer again." The reply goes through the channel's `<channel>.reply` as Taktus itself
(ADR-0033). It quotes the participant's own words, and no model wrote it, so it is not a
message step under ADR-0142. It carries the tenant's label where the tenant set one.

The reading is kept in the object store. The block names it by digest, and the account by its
digest. `step.answer_read` records it, outcome `read` or `unread`.

The same account then answers `yes`, `ja` or `confirm`: the step succeeds. A `no` withdraws the
reading, and the participant is asked again. Any other text is a new answer, and is read
again. A yes with no reading pending is read as an answer.

### 5. The result names who answered as the channel names them

A confirmed answer is the step's result:

```json
{"participant": "supplier", "answer": "Delivered on Friday.", "option": null,
 "answered_by": {"channel": "channel.mail", "account": "sha256:…"}}
```

The step ends `succeeded` with method `human`. `step.finished` names `participant:<role>` as its
actor, never the account: the ledger stays without content and without a channel's account
(ADR-0006, ADR-0040 §7). The account is in the result, by digest in the provenance record. The
steps after it read the answer through `$from`.

### 6. Nothing else of a participant acts

The answer settles this one step and nothing more. A participant has no identity, no role and
no right. A person of the tenant cannot confirm the step on the participant's behalf: the
answer is the participant's, in their channel. `taktusctl` and the HTTP surface refuse it.

### 7. A rehearsal asks no participant

A rehearsal sends nothing (ADR-0030). The step ends `rehearsed`, its result
`{"participant": …, "rehearsed": true}`.

## Alternatives

- **A Taktus account for every participant.** ADR-0040 links an account to an identity. A
  supplier who answers once a quarter would have to register, and would then be an actor of the
  tenant. Rejected: the issue asks for no account, and an actor is more than an answer needs.
- **A decision request to an external decider.** A decision request decides an anchor and is
  answered by a role of the organisation (ADR-0042). Its answer becomes a register entry. An
  outside party decides nothing of the organisation's. Rejected.
- **Match the answer by the sender's address.** An address can be set by anybody, and
  ADR-0040 refuses it for that reason. The thread is the conversation Taktus opened.
- **Let the participant's answer through without reflection.** ADR-0008 forbids acting on free
  text silently, and a delivery date read wrongly is a wrong commitment.
- **A model reads the answer.** A reading by rule is reproducible. A process that needs a
  model's reading reads the confirmed text in a step after it.

## Consequences

- `run/domain/model/work.py`: `ParticipantWork`, the work of a `human` step. `parse_work` reads
  it. A `human` step without it is still refused.
- `run/domain/model/block.py`: the cause `awaiting_participant` and `Awaited` on `OpenBlock`.
- `run/domain/service/participants.py`: the reading and the replies, pure.
- `RunEngine.answer_participant`; `composition/participants.py`, `ParticipantAnswers`, ahead of
  the owner-facing channel's answers in the daemon.
- The ledger kind `step.answer_read`.

## Where this promise ends

- **The thread is the channel's word.** Whoever can write into the thread can answer first. On
  mail that is whoever the question reached, and whoever they forwarded it to. A process that
  must know who answered names the participant's address in its question and checks the
  account in the step after it.
- **A participant who never answers leaves the run waiting.** The process's deadlines bound it
  (ADR-0133). This decision adds no timeout of its own.
- **The reflection reaches the channel only where its connector declares `<channel>.reply`.**
  Elsewhere the reading is kept, and the participant is not told. A failed reply is not retried.
- **A reading by rule is literal.** "Not confirmed" names the option `confirmed`. A process that
  offers options chooses words that do not contain each other.
- **One thread, one step.** Two steps that expect an answer in the same thread both wait. The
  first found takes the answer.
- **Only connector intake reaches it.** An answer through the web app or the command line is not
  a participant's answer.
