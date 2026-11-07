# ADR-0261 — A rollout channel serves an assistant, and a message there is never a command

**Status:** accepted · extends ADR-0040 (the identity rule), ADR-0048 (event reactions), ADR-0142 (the outward message), ADR-0163 (a shared agent) and ADR-0264 (on behalf of a person) · UC-12.1 §2 · DEC-0228

## Context

UC-12.1 asks that an organisation rolls out an assistant into its own communication tool: a
company chatbot in its team chat, for example. Two kinds of channel are distinguished there. In
a **command channel** a person commands Taktus with their own rights (UC-1.7). In a **rollout
channel** a person uses an assistant, which acts with the agent's rights and the person's own
credentials. A message in a rollout channel never becomes a command, and it cannot start,
change or stop any process other than the assistant's own.

Every channel so far was a command channel. A message a connector accepted from a person the
identity component placed was kept as an intake event and written to the outbox as
`intake.accepted`. The automation role then matched it against every process's event triggers
and completed it into a command (ADR-0048). A message in the thread of something Taktus asked
was taken as an answer to it (ADR-0045).

A shared agent exists (ADR-0163). Its core names the process it runs, its **flow**, and the
most it may do, its **grants**. A role's profile narrows the grants. A call resolves the
caller's profile from their roles and runs the flow as the caller. A step can read a source
with the credential of the identity the run acts for (ADR-0264).

Two words are used below. An **assistant** is a shared agent rolled out into a rollout channel.
A **conversation** is the place in a channel a message was written in: a channel of a team
chat, as the event's context field `conversation` names it (`contracts/events/v1` §1).

## Decision

### 1. Every channel is configured as one of the two

The instance's configuration `TAKTUS_ROLLOUT` names the rollout channels. Each entry maps a
channel capability, or a capability and one conversation of it, to the agent it serves:
`channel.chat/C0HELP=helpdesk`. An entry for a conversation holds before an entry for its
capability. A channel or a conversation no entry names is a command channel. Rolling out into
a further conversation, or into a further channel a connector serves, is one more entry. No
code changes.

### 2. A message in a rollout channel is kept for the assistant

The intake asks which kind of channel a message arrived in before anything else is done with
it. In a rollout channel:

- a message a placed person wrote is kept as an intake event of status `assistant`, and the
  outbox entry `intake.assistant` names it and the agent, in the same transaction. Nothing is
  written as `intake.accepted`, so no process's trigger is matched against it;
- it is never taken as an answer to something Taktus asked, and it is never completed into a
  command: `CompleteIntake` refuses an event of status `assistant` with `NotACommand`;
- a sender nobody could place is answered as anywhere else: offered how to link their account
  (ADR-0040). They get no assistant;
- a message its sender did not write, or one from an automation, is passed over. Nothing is
  kept.

### 3. The assistant's own process runs as the person

The automation role reads `intake.assistant` on its pass. For each entry it starts the agent's
flow once, as a call of the agent (ADR-0163 §3): the profile is resolved from the person's
roles, `agent.called` records it, and the run acts as the person. The call is commissioned as
every call of an agent is: the record that commissions its plan names the call of the agent,
never the message, and the message is one of the run's inputs. The run's identifier is
derived from the tenant, the flow and the event. A redelivery, a restart or a second leader
names the same run, which the engine refuses to create twice.

The run is given the message in the input `message`, and the reply address in the inputs
`reply_address` and `reply_thread`, as far as the flow's version declares them. A version that
declares no input `message`, or that requires an input none of the three is, is no assistant's
process. The call is then refused.

### 4. The agent's grants cap what the person's credential reaches

Before the flow starts, every tool action its steps use is checked against the profile's
grants. A tool action is a capability a step requires, or a connector operation a step calls.
An operation is granted when the profile grants it or its capability. A flow that uses one the
profile does not grant is refused before anything runs. So a person's credential never reaches
further than the agent may.

A step of the flow that reads `on_behalf` reads with the person's own credential (ADR-0264). A
person without one gets nothing from that source.

### 5. The answer is the process's

The assistant answers through a step of its own process. That step calls the channel's reply
operation with the reply address the run was given. It is an outward message under its frame
(ADR-0142): checked by a step of its own, classified for promises, labelled, and held by the
tenant's delay and quiet hours. Nothing outside the process speaks for the assistant.

One exception holds. When the call is refused, the person is told so in the channel by one
sentence of the instance: the assistant is switched off, none of their roles may use it, or it
would need more than it may do. The refusal is recorded as `agent.refused`, with the reason as
its outcome.

### 6. An assistant is switched off and exported like any process

An assistant is switched off by switching off its flow (UC-13.6). A message then starts nothing,
and the person is told that the assistant is switched off. Its flow's versions, its core and its
profiles are rows of the tenant, carried by the tenant's export (ADR-0221).

## Alternatives

- **The instance answers with the run's result when it ends.** It is shorter: no reply step in
  the process. But a text a model wrote would then reach a channel outside any step, past the
  frame of ADR-0142, and outside what the process's autonomy statement governs.
- **A rollout channel as a property of the process.** A process would name the conversations it
  serves. Then a process version would change for every rollout, and two processes could claim
  one conversation. The channel is the instance's configuration, as a connector is.
- **A message in a rollout channel as a command the assistant's process is triggered by.** It
  would reuse the trigger path. It would also let any process with a matching trigger start from
  a rollout channel, which UC-12.1 forbids.

## Consequences

- `components/command/domain/model/intake.py`: the status `assistant`.
- `components/command/application/service/receive_intake.py`: the rollout channels, the event
  kept for the assistant and `intake.assistant`; `complete_intake.py`: `NotACommand`.
- `ports/outbox.py`: the topic `intake.assistant`.
- `composition/agents.py`: the grant check over tool actions, and a call started for a
  message; `composition/assistants.py`: the assistant served for a message, and the refusal
  said; `composition/reactions.py`: the entries `intake.assistant` read on the pass.
- `composition/settings.py`: `TAKTUS_ROLLOUT`, read by the intake of `taktusd`.
- `blueprints/knowledge/processes/K-02-answer-in-the-chat.yaml`: an assistant's process.
- Tests: `tests/composition/test_rollout_channels.py`.

## Where this promise ends

- **A conversation is what the event's context names.** A connector whose events carry no
  `conversation` is classified by its capability alone. All of it is then one kind of channel.
- **The connectors an agent grants are not checked before a start.** The pool resolves a
  connector by capability at the step, and the profile's tool actions are what is checked.
- **The answer is as fast as the tenant's message rules allow.** The delay and quiet hours of
  ADR-0142 hold an assistant's answer as they hold any outward message. A chat assistant wants
  a short delay, and the delay is the tenant's to set.
- **The person must hold a role with a profile.** A person whose roles have no profile of the
  agent is refused, as any caller is (ADR-0163 §3).
- **The message is an input of the run.** It is kept with the run as every input is. The
  ledger stays content-free (ADR-0006).
- **Use is counted by profile, never by person** (principle 14). The run acts as the person,
  as a run started by them does, and nothing measures the person.
