---
id: UC-1.13
title: A person sees what they may ask Taktus for
component: command
epic: E1
serves: [P1, P4, P10, P14]
state: verified
version: 0.6.0
tests: [tests/components/reporting/test_catalogue.py::test_each_entry_carries_the_one_command_and_how_to_start_it_on_each_channel, tests/components/reporting/test_catalogue.py::test_without_a_chat_that_reads_a_start_and_without_any_process, tests/components/reporting/test_catalogue.py::test_no_entry_holds_a_queue_a_ticket_or_a_promised_time, tests/components/command/test_start_command.py::test_two_channels_issue_the_same_intent_and_context_and_differ_only_in_where, tests/adapters/rest/test_catalogue.py::test_the_catalogue_lists_what_the_reader_may_start_and_how_on_each_channel, tests/adapters/rest/test_catalogue.py::test_a_start_from_the_web_app_is_the_command_the_cli_and_an_agent_issue, tests/adapters/rest/test_catalogue.py::test_a_process_the_reader_may_not_see_is_answered_as_one_that_does_not_exist, tests/composition/test_catalogue_in_channel.py::test_the_catalogue_is_listed_with_what_to_write_and_what_a_reply_cannot_give, tests/composition/test_catalogue_in_channel.py::test_a_start_is_read_back_and_runs_only_on_yes_as_the_person_on_the_channel, tests/composition/test_catalogue_in_channel.py::test_a_start_dropped_with_no_starts_nothing, tests/composition/test_catalogue_in_channel.py::test_an_unseen_process_one_that_needs_an_input_and_an_outsider_are_refused_alike]
adrs: {ADR-0008: e6a4e033abd4, ADR-0131: 7b1cf7e37d35, ADR-0159: 539eaa9000a6}
supersedes: null
---

# UC-1.13 — A person sees what they may ask Taktus for

## 1. What must be achieved

A person sees a list of the processes they may start: what each is for, what it needs from them,
and how to start it. Starting one from the list is the same ordinary command that a request from
the chat, the command line or the person's own agent would issue. The list works through every
channel a person reaches Taktus by. It is a list and a way to start, never a ticket portal.

## 2. How it is verified

- The list holds every process with an active version that the person may see (UC-6.4), and no
  other. A process of another tenant is never in it.
- Each entry names what the process is for, the inputs it needs, the level it runs at, the roles
  a person acts in along it, and how to start it on each channel.
- A start from the list issues the same command as a start from the command line and from the
  person's own agent: the same intent, recognised the same way, with the same inputs and the same
  identity. Only the channel and the reply address differ. A test compares the three commands.
- In the chat, the person asks for the list and gets it, and asks to start an entry. The start
  is read back and takes effect only once the same person confirms it (ADR-0008).
- A start of a process the person may not see is answered exactly as one of a process that does
  not exist, and starts nothing.
- No entry and no start keeps a ticket, a queue position, a priority or a promised time. A start
  is a run, and the run's own view tracks it.

## 3. Where the boundary lies

**Not a service desk.** No tickets, queues or service-level agreements (principle 1). Where an
organisation runs a ticket or request system, mirroring a request there is UC-5.3's. **Not new
rights.** Who may see a process is UC-6.4's; what a person's own agent may do is UC-1.11's.
**Not a catalogue of adapters or blueprints.** Which workers, connectors and models exist is the
catalog component's; a first process is chosen from the gallery (UC-10.4). **Not a request for a
new process.** Where nothing fits, the list points to the dialogue that proposes one (UC-1.2).

## 4. What it rests on

Commands from any channel (UC-1.1); every command belongs to one identity (UC-1.7); a person's
own agent (UC-1.11, ADR-0131); what each role sees (UC-6.4); the confirmed reading of free text
(ADR-0008); the owner-facing channel (UC-6.11). The owner accepted it as F9 of the product
outlook (DEC-0190), and issue #340 carries it. ADR-0159 §1 to §3 is how it is built. The version
is `0.6.0`, the milestone DEC-0190 places it in.

## 5. What is proven so far

The list is `GET /catalogue` and the web app's page `#/catalogue`; each entry carries the one
start command, `run <process>@<version>` recognised as `process.run`, and how to start it in the
web app, the chat and the person's own agent. A start from the web app, from the agent and from
the command line issues the same intent, context and identity — by the named tests. In the
owner's conversation the list is asked for and an entry started on a confirmed reading; an
entry that needs an input is listed with it and started elsewhere. A process another tenant holds
is neither listed nor started, and is answered as one that does not exist. No entry carries a
ticket, a queue or a time. The chat answers only in the owner's conversation (ADR-0159, *Where
this promise ends*).
