# ADR-0142 — An outward message is labelled, checked by a step of its own, and held by rule

**Status:** accepted · extends ADR-0024 (connector effects), ADR-0022 (egress), ADR-0042 (anchors), ADR-0103 (a parked run) and ADR-0130 (the frame) · issue #435, UC-7.6

## Context

A message to a customer cannot be taken back once it is sent. UC-7.6 asks for one frame around
every such message, enforced by the run and not asked of a model. Its conditions are: a label
on what a model wrote; a send decision made by a rule over named yes-or-no checks; a second
check in a step of its own, which sees the draft and the raw tool results and may only send or
reject; a sending delay and the tenant's quiet hours; no send once a person has answered in the
case; a person's decision on a message that promises a date, a feature or legal advice, and on
one to more recipients than the tenant's limit; and an egress entry that names the case, the
checks and the label.

Four words are used below. A **delivery** is a connector operation whose declared effect is
`delivery`: a message reaches someone through a channel (ADR-0024 §3). A **drafting step** is a
step of method `llm` whose answer a step reads through `$from`, directly or through steps that
are not themselves `llm` steps. A **message step** is a connector step that sends a message
under this frame. The **case** is what a person may answer in: a ticket, a thread, a review.

## Decision

### 1. Which steps are message steps

A connector step is a message step when its operation is a delivery and a drafting step stands
behind its input, or when its work declares `message`. A delivery that a drafting step stands
behind and that does not declare `message` is refused at its boundary: nothing is sent, the
step fails without a retry, and `message.held` records the outcome `undeclared`.

A connector write is a record, not a message (ADR-0024 §3). It enters the frame only by
declaring `message`. A delivery no model wrote and that declares nothing is sent as the process
says, under the recipient limit of §6 alone.

### 2. The step declares its frame

A message step's work carries `message` beside `when` and `scope`. The run reads it, never the
operation (`components/run/domain/model/work.py`):

```yaml
message:
  text: text                     # the input field that is the message's text
  checks:                        # the named yes-or-no checks, one at least
    facts_match: {value: {$from: score, $select: facts}, equals: "yes"}
    tone: {value: {$from: score, $select: tone}, equals: "yes"}
  check: verify                  # the independent check (§4)
  classification: promises       # what classifies a promise (§5); optional
  case: {$input: ticket}         # the case, from the intake; optional
```

At the start of a run the engine refuses a declaration whose checks are empty, whose
`check` or `classification` is not a step the message step depends on, or whose `case`
does not come from the run's inputs. A `case` has the shape of ADR-0130's subject: one
`$input`, with a `$select` at most. Without a `case` the step's scope subject is the case. A
step with neither has no case.

### 3. The send decision is the message step's own rule

A connector step is of method `rule` (ADR-0024). The send decision is therefore made by the
message step itself, before it calls anything. Each named check is a condition in the shape of
the conditions of a rule `check`. The message is sent only when every check holds. A check that does not hold
fails the step without a retry: nothing is sent, the run escalates to a person, and
`message.held` records the outcome `checks`. A model may score a dimension in a step before. The
decision is the rule's and never a model's.

### 4. The independent check is a step of its own

`check` names the step that checks the draft. The run holds it to four conditions before
the run starts:

- it is not a drafting step of the message;
- it reads, through `$from`, only the drafting steps' answers and connector steps' results: the
  draft and the raw tool results, and no other step;
- it is a step of its own, so a check of method `llm` is a model call of its own, with its own
  prompt and context. The drafting step's trace is kept outside the ledger and is never a
  result (ADR-0135), so the check cannot read the drafting step's reasoning;
- its answer is read by a rule with exactly two outcomes: `send` or `reject`, after spaces and
  case are set aside.

An answer of `reject`, or any answer that is neither, fails the message step without a retry
and records `message.held` with the outcome `rejected`.

### 5. A promise is held for a person

`classification` names the step that classifies the message. The classification may be a
model's. The rule reads its answer as words: `none` alone is no promise; `date`, `feature` and
`legal_advice` are each a promise. Any other answer cannot be classified. A message classified
as a promise, one that cannot be classified, and one whose step declares no `classification`
are held for a person.

The frame's own anchor `anc-promise` holds it at the step boundary. It is of class `legal` and
decided by the role `owner`. It is raised at every level, whatever the tenant configured, as
the anchor of ADR-0130 §6 is. Its decision request is the one every anchor has (ADR-0042).

### 6. Mass sending is held for a person

Any outward connector step may declare `recipients`: a list, a text, or a count, with
references. The rule counts a list by its distinct items, a text as one, and a count as given.
A value it cannot count is held as if it were over the limit. An outward step that declares no
recipients addresses one. More recipients than the tenant's limit raise the frame's anchor
`anc-mass-sending`, of class `legal`, decided by the role `owner`, at every level. A message
step and any other outward step are both held by it.

### 7. The label

The tenant configures the label's wording. Taktus adds it to the message's `text` field, as a
paragraph of its own after the text, before the call. A message step whose text a drafting step
stands behind is refused when the tenant configured no label. The refusal happens before the
connector port is called, and again at the call: a label withdrawn while the message waited is
refused too. The step fails without a retry, and `message.held` records the outcome
`unlabelled`.

### 8. The delay and the quiet hours

A message is **approved** when it has passed every check, the independent check, every anchor
of §5 and §6 and the confirmation of its level. From then it waits for the tenant's delay. It
is sent at the first moment after the delay that lies outside the tenant's quiet hours, read in
the tenant's zone. Quiet hours are a span of the day, and may run across midnight.

The step waits at its boundary. Its block is booked to `wait.external` with the cause
`holding_message`, and carries when it is checked next. `message.delayed` records the hold,
with the outcome `delay` or `quiet_hours`. The run halts with the cause `parked`, and its
runner defers the job to that moment (ADR-0103). A restart loses nothing: the block holds when
the hold began and when it ends. A runner that wakes inside quiet hours holds the message again
until they end.

### 9. A person's answer in the case

A person who answers in the case is recorded as such: `taktusctl case answered PROCESS CASE`
writes a `CaseAnswer` of governance and the ledger entry `case.answered`. Before a message step
starts, and again before it sends after a hold, the run asks whether a person answered in the
step's case for its process. If one did, the message is not sent. The step ends without its
act, with the result `{"sent": false, "because": …}`, and `message.held` records the outcome
`answered`. Every later message of that process in that case is held the same way. A message
without a case is not held by an answer.

### 10. The record of what was sent

A message that was sent writes its egress entry as every delivery does (ADR-0022 §4). In the
same transaction `message.sent` names the same run and step. Its `content_digest` is the digest
of the message's record: the case, each check and its outcome, the check step and its verdict,
the classification, the recipients' count, and the label. The ledger stays content-free
(ADR-0006): the record is an object in the store, and its digest is in the entry.

### 11. The tenant's message rules

`MessageRules` (governance) keeps per tenant the label, the delay, the quiet hours with their
zone, and the recipient limit. `taktusctl messages show|set` shows and changes them, and
`messages.configured` records a change and who made it. A tenant that configured nothing holds
the shipped default (NTC-0234): no label, a delay of 600 seconds, no quiet hours, and a limit of
10 recipients. Without a label no message a model wrote is sent.

### 12. A rehearsal asks none of it

A rehearsal acts on nothing outside and asks no anchor (NTC-0079). It asks nothing of this
frame either: no check, no hold, no anchor, no answer. Its message steps answer from the
recording of their last real call, as every outward step of a rehearsal does (ADR-0030).

## Alternatives

- **The independent check of another method kind than the draft's, a rule for an `llm`
  draft.** UC-7.6 asks for "its own model call and context". A rule cannot read a draft against
  tool results in words. Independence is that of the step, its call and its context. The kind
  of method is left to the process.
- **The send decision as a step of its own before the delivery.** A rule step would produce a
  verdict, and the delivery would have to be held to it all the same. The delivery is already a
  rule step. A decision made where the act happens cannot be bypassed by a process that forgets
  to read it.
- **The label carried in the call's context for the connector to add.** A connector that
  ignores the field would send an unlabelled message, and the run could not tell. Taktus adds
  the label to the text and knows that it did.
- **Every outward write a model drafted as a message.** A record written to a repository or a
  ticket's field is not a message to a person, and the processes of this repository write such
  records under their own checks. The connector's declaration draws the line (ADR-0024 §3),
  and a write that is a message declares `message`.
- **A held message failing its step.** A person who answered in the case took it over. Failing
  the step would escalate a run that went as it should. The step ends without its act, as a
  step whose `when` did not hold does (ADR-0088).
- **The delay as a `wait` step the process declares.** A process could leave it out. The hold
  is the frame's, and the tenant sets its length.
- **The case's answer read from the channel by the run.** Only the connector knows how a
  person answers in a helpdesk or a thread. A record a person or an intake writes is the one
  thing the run can ask the same way for every channel.

## Consequences

- `run`: `Message` and `recipients` in a step's work; the domain service `messages`, the port
  `Messages`, the cause `holding_message`; the engine's boundary in `_message_gate` and its
  call in `_connector_call`. Ledger kinds `message.held`, `message.delayed`, `message.sent`,
  `messages.configured` and `case.answered` (`LedgerEntry.json`).
- `governance`: `MessageRules`, `CaseAnswer` and the use case `TenantMessages`; the run reaches
  it through `MessagesOfTheRun` (`composition/decisions.py`). `taktusctl messages` and
  `taktusctl case`.
- Migration `0074` adds `message_rules` and `case_answer`.
- `tests/components/run/test_outward_messages.py` and
  `tests/components/governance/test_messages.py` prove the eight conditions of UC-7.6 §2.

## Where this promise ends

- **A message is what the connector declares a delivery, or what a step declares a message.**
  A connector that declares `write` for an operation that sends a message keeps it out of the
  frame unless its step declares `message` (ADR-0024, *Where this promise ends*).
- **The label is added to the field `message.text` names.** A channel that renders another
  field, or drops a paragraph, may show the message without it. Its wording, and what the law
  asks it to say, are the tenant's (UC-7.6 §3).
- **Drafting is known by method.** A message a `worker` or a `neural` step wrote is not
  recognised as written by a model, and is labelled only when its step declares `message` and a
  label is configured. A drafting step is found through `$from`. Text a model wrote that reaches
  the message through an artifact of a worker, or through the run's inputs, is not found.
- **The independent check is as independent as its process makes it.** The run holds what it
  reads and that it is a step of its own. The same model may answer it, in a new call with a new
  context. Whether its prompt checks the draft well is the process author's, and its evaluation
  cases are UC-4.18's.
- **Recipients are counted where the step names them.** An outward step that names none counts
  as one. A list address that the channel expands to many is one recipient to the rule.
- **A person's answer is known when it is recorded.** No connector's intake records
  `case.answered` yet. Until one does, a person or a process records it with `taktusctl case
  answered`, and an answer given in the helpdesk alone does not hold a message.
- **The hold is checked when the runner wakes.** A message is sent no earlier than its moment,
  and later by however long the runner takes to claim the job. A message is held from approval,
  so a run that waited for a person's decision waits for the delay once more after it.
- **The anchors are decided by the role `owner`.** A tenant cannot yet name another role for
  them, as for the anchor of ADR-0130.
- **A rehearsal asks none of it** (§12). A rehearsal of a message step proves nothing about its
  checks, its hold or its anchors.
