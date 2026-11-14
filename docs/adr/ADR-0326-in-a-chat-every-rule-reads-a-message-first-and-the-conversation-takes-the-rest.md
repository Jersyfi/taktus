# ADR-0326 — In a chat every rule reads a message first, and the conversation takes the rest

**Status:** accepted · extends ADR-0325, ADR-0069, ADR-0304 · UC-1.14, DEC-0239

## Context

In a chat Taktus reads, a message from a person passes through rules. The owner's conversation
reads an answer to a report, a request to show something, a session, the catalogue, a question
about spend, a take-over, and a change in dialogue (ADR-0069, ADR-0091 §6, ADR-0128 §7, ADR-0159
§3, ADR-0304). Each rule reads its own words from the tenant's phrasebook. A message no rule
reads goes on as an event: a process whose trigger names `message.posted` or `message.mentioned`
starts on it (UC-4.14).

DEC-0239 wants Taktus's own conversation in the chat too (ADR-0325). Two things must not change:
a phrasebook word keeps meaning what it means, and a process a tenant set to start on a message
keeps starting.

## Decision

### 1. The conversation reads last

The conversation is the last reader of the owner's conversation. It takes a message only when
all of these hold:

- the operator named a conversation process (ADR-0325 §3);
- every rule before it passed the message over;
- the sender is a person the identity component placed;
- no active process version of the tenant has a trigger on the message's kind of event.

Otherwise it passes the message over, and it goes on exactly as before.

### 2. A turn in a chat is answered in the chat

The turn is kept with where it came from: the channel, the address, the thread. The run's last
step says the answer there, with the act read back and "Answer yes to do it, or no." The
reporting component delivers it and records the delivery, under a key derived from the run, so
that a repeat says it once. An answer that would carry a secret value is not said; the chat is
told the web page shows it.

### 3. A yes in the chat does the act

A message that is one of the phrasebook's `yes_words` or `no_words`, while an act proposed in
that chat waits, settles the latest such act, as the web's buttons do. What came of it is said
in the chat. The words are the tenant's: no new phrasebook entry is needed.

## Alternatives

- **The conversation before the rules.** Rejected: "show run 12" would become a question to a
  model, costing a run and possibly answered wrong, where a rule answers exactly.
- **A word of its own, `ask: …`.** Rejected: DEC-0239 asks for a conversation as easy as a chat
  assistant. A person should not have to know a word to be answered.
- **Taking every message no rule reads.** Rejected: a process set to start on a message would
  stop starting.

## Consequences

- `OwnerAnswers` gains its last reader (`converse_with`); `ConversationInChat` is it
  (`composition/conversation.py`).
- A tenant that names a conversation process and posts in a channel Taktus reads gets an answer
  to every message no rule and no trigger takes. That is intended. A tenant that wants silence in
  a channel leaves the setting unset, or gives the channel a process.

## Where this promise ends

The check for a trigger asks whether an active version names the message's kind of event; it
does not evaluate the trigger's filter or condition. A process with a filtering trigger on
`message.posted` therefore keeps every such message from the conversation, including the ones
its filter would not take. The yes of §3 settles only an act proposed in the same channel; one
proposed on the web is settled on the web. A message that is a yes and arrives while no act
waits is a turn like any other.
