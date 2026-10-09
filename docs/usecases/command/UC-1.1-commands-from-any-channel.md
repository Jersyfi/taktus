---
id: UC-1.1
title: Commands from any channel
component: command
epic: E1
serves: [P1, P4]
state: building
version: 0.2.0
tests: [tests/components/command/test_complete_intake.py::test_the_link_places_the_event_and_completes_it_as_the_linked_identity, tests/adapters/connectors/test_chat_channel.py::test_the_chat_channel_is_added_by_configuration_and_a_connector_alone, tests/adapters/connectors/test_chat_channel.py::test_the_same_instruction_through_two_channels_is_the_same_command, tests/adapters/connectors/test_chat_channel.py::test_a_reply_is_delivered_into_the_thread_the_command_arrived_in]
adrs: {ADR-0003: d0268914fed9, ADR-0024: a8baa5bc69f3}
supersedes: null
---

# UC-1.1 — Commands from any channel

## 1. What must be achieved

A person gives Taktus a task where they already work: as a mention in a comment of their ticket
system, in their knowledge tool, on the command line, in the web app, on the desktop or on the
phone. Taktus turns every such input into the same kind of command, so that what happens next
does not depend on where the task came from. The answer, or a question back, arrives in the
channel the task came from.

A new channel is added without changing the core. Turning an input into a command is Taktus's
own work: no foreign gateway or agent runtime does it in Taktus's place.

## 2. How it is verified

- The same instruction arriving through two different channels produces two commands that are
  equal in every field except the channel and the identity of the message.
- Every command carries the identity of its sender, its context and the address a reply goes
  to.
- A reply or a question about a command is delivered through the channel the command arrived on,
  to the thread or conversation it arrived in.
- A channel is added by adding a connector that implements the intake half of the connector
  contract (ADR-0024); a test adds a channel this way and changes nothing under
  `src/taktus/components/`.
- A channel is referred to by its capability, never by a product name (ADR-0003).
- The normalisation of an input into a command is part of the `command` component. No foreign
  gateway or runtime product performs it; a library for a channel may be used only inside that
  channel's connector.

**Proven so far:** an event arriving through a channel becomes a command that carries its
channel and the address a reply goes to, by the named test. That every command carries its
sender's identity and its context is not checked as a condition of its own. The equality of two commands from two
channels is not tested; a reply delivered to that address, and a chat channel, are not built. That the normalisation is
Taktus's own is held only as far as the architecture tests see a foreign import in the core.

## 3. Where the boundary lies

**Not planning.** Working a plan out with the person is UC-1.2; this use case ends when the
input is a command. **Not authorisation.** Whether the sender may give the command is the
identity component's; that the command carries who sent it is this use case's. **Not every channel.** Which channels ship when is the roadmap's;
this use case requires that any channel can be added, not that all exist. **Not delivery
guarantees** of the channel itself.

## 4. What it rests on

The connector contract and its intake half (ADR-0024); the adapter obligation (ADR-0003);
`taktusctl submit` and the webhook intake of `0.1.0`; the chat connector of `0.2.0`, hence the
version. Definition `UC-1.1`, and chapter 5.4 of the definition, which keeps the normalisation in
the core and no foreign gateway product as its base (NTC-0050).
