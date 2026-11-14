---
id: UC-1.14
title: A person builds in Taktus by conversation
component: command
epic: E1
serves: [P2, P7, P9, P10, P14]
state: built
version: 1.0.0
tests: [tests/composition/test_conversation.py::test_a_turn_runs_as_a_budgeted_process_and_its_act_waits_for_the_yes, tests/composition/test_conversation.py::test_an_act_off_the_list_a_wrong_form_and_a_no_change_nothing, tests/composition/test_conversation.py::test_the_model_produces_no_exact_value, tests/composition/test_conversation.py::test_in_a_chat_a_rule_or_a_trigger_comes_first_and_a_yes_there_does_the_act, tests/composition/test_conversation.py::test_every_rule_of_the_owners_conversation_reads_before_the_conversation, tests/composition/test_conversation.py::test_the_conversation_proposes_from_the_list_the_agent_is_offered_as_tools, tests/adapters/rest/test_conversation.py::test_without_a_conversation_process_a_turn_is_refused_and_a_key_is_needed, tests/adapters/rest/test_conversation.py::test_an_act_read_back_is_done_only_on_its_persons_yes_and_once]
adrs: {ADR-0008: e6a4e033abd4, ADR-0324: 543aa33782ff, ADR-0325: 978aeac4763b, ADR-0326: 2f46e33ad8f4}
supersedes: null
---

# UC-1.14 — A person builds in Taktus by conversation

## 1. What must be achieved

A person talks to Taktus as they would to a chat assistant, in the web app and in a chat, and
gets short answers. Through the conversation they build: they plan a process, ask for a change
or a description of one, have a proposal rehearsed and commissioned, roll a process back, or
start one. Taktus leads the conversation itself, over its own model port; a vendor's agent
program never leads it (DEC-0239, `docs/vision/non-goals.md`). Nothing Taktus proposes in a
conversation is done until the person says yes.

## 2. How it is verified

- A person writes to Taktus in the web app and in a chat, and Taktus answers in words in the
  same place.
- Every turn runs as a process of its own, acting as the person, under a budget, with its steps
  in the ledger.
- Taktus proposes acts only from one closed list, the same that a person's own agent is offered
  as tools (UC-1.11). An act off the list is not kept, and the answer says so.
- A proposed act is checked by a rule, read back to the person, and done only once the person
  says yes. A no does nothing. An answer that cannot be read is said to be one, and proposes
  nothing.
- No value a language model produces in a conversation is of the class `exact`.
- A conversation belongs to no project, and is the same one whether the person writes from the
  web app or a chat.
- In a chat, every rule of the owner's conversation reads a message first, and a process that
  starts on that kind of message keeps starting; the conversation takes only what is left.
- Nobody reads another person's conversation, and nobody settles another person's act.
- Without a conversation process named on the instance, no turn is taken, and the person is told
  which setting names one.

## 3. Where the boundary lies

**Not an agent that acts alone.** Taktus proposes one act per answer and does it only on the
person's yes; it does not chain acts. **Not knowledge of everything.** The conversation answers
from the message, the turns before it, the list of acts and the names of what the person may
see; what a run produced or a document says is not read. **Not a session in a project.** A
session with a project's knowledge, each statement sourced, is UC-1.8. **Not steering.**
Pausing or cancelling a run and the emergency stop stay with UC-1.5 and UC-7.2.

## 4. What it rests on

Commands from any channel, the conversation Taktus's own (UC-1.1); a person's own agent and its
tools (UC-1.11, ADR-0324); the decision request's reading confirmed before it counts (ADR-0008);
a turn as a run of S-09 (ADR-0325); the chat's rules first (ADR-0326). The owner asked for it in
DEC-0239 ("Beides, Taktus führt"); it is numbered in NUMBERING.md by NTC-0291. The version is
`1.0.0`, the milestone package F lands in.

## 5. What is proven so far

A turn runs as S-09 as the person, under its budget, its entries in the ledger; the model is
told the message, the list of acts and the processes the person may see; the act it proposes
is read back and done only on the yes, a no and an act off the list and an answer not in the
agreed form change nothing; S-09's model step is `free`; in a chat a process triggered by the
message keeps it, the answer is said in the thread and a yes there does the act; every rule of
the owner's conversation reads first; the list is the agent's tools; nobody settles another
person's act, and without a conversation process a turn is refused naming the setting — by the
named tests, with a scripted model. Not proven: a turn answered by a real model on the live
instance, and the page "Ask Taktus" used by a person; both need the instance with the setting
`TAKTUS_CONVERSATION_PROCESS` and S-09 registered.
