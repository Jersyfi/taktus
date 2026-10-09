---
id: UC-6.11
title: The owner-facing channel
component: reporting
epic: E6
serves: [P4, P7, P10]
state: building
version: 0.2.0
tests: [tests/components/reporting/test_owner_channel.py::test_every_kind_produces_three_renderings_that_agree, tests/components/reporting/test_owner_channel.py::test_the_repository_text_holds_what_future_work_needs_and_no_conversation, tests/components/reporting/test_owner_channel.py::test_the_message_is_in_the_configured_language_and_links_everything, tests/components/reporting/test_owner_channel.py::test_a_report_without_one_of_the_four_is_not_sent, tests/components/reporting/test_owner_channel.py::test_an_answer_is_filed_only_after_its_reading_is_confirmed, tests/components/reporting/test_owner_channel.py::test_a_decision_answer_is_filed_in_the_register_only_once_confirmed, tests/components/reporting/test_owner_channel.py::test_an_answer_no_offered_answer_can_be_read_from_is_asked_back, tests/components/reporting/test_owner_channel.py::test_an_answer_from_anyone_else_is_acknowledged_as_not_filed, tests/components/reporting/test_owner_channel.py::test_the_report_also_goes_to_a_configured_ticket_system_as_a_task, tests/components/reporting/test_owner_channel.py::test_closing_the_task_without_an_answer_files_nothing, tests/components/reporting/test_owner_channel.py::test_a_message_that_cannot_be_delivered_leaves_the_event_and_shows_the_failure, tests/components/reporting/test_owner_channel.py::test_a_failure_taktus_noticed_about_itself_reaches_the_owner_the_same_way, tests/components/reporting/test_owner_channel.py::test_no_message_carries_a_secret_value, tests/adapters/connectors/test_owner_channel_chat.py::test_the_owner_answers_in_the_thread_and_the_answer_is_filed_once_confirmed, tests/adapters/rest/test_owner_reports.py::test_the_view_and_the_repository_text_carry_the_same_report]
adrs: {ADR-0006: 4ef70c98354b, ADR-0008: e6a4e033abd4, ADR-0017: c932691e9072, ADR-0028: 84461cdccb02, ADR-0045: e1fcb1254c71}
supersedes: null
---

# UC-6.11 — The owner-facing channel

## 1. What must be achieved

Whatever Taktus needs from the owner of a project — a decision, something only the owner can provide, a
date — reaches the owner where the owner is, and the owner's answer reaches the place where it is
needed.

One event has three renderings:

- **a repository text** — in English, minimal and durable, holding only what the code and future work
  need;
- **a message in the channel the owner chose** — in the owner's language, with the context needed to
  act and links to the files, issues and pull requests concerned;
- **a view in the web app**, with its history.

The owner answers in the channel. Taktus files the result where it belongs — a decision record, a
comment on a pull request, code. An answer given in chat becomes a record in the way every free-text
answer does: Taktus interprets it, reflects its interpretation back, and acts only on the confirmed
interpretation.

A report names what is needed, the steps to provide it, which work is standing still for want of it,
and by when it is needed. Where an organisation runs a ticket system, the same report goes there as a
task. The channel is configuration, not architecture. For the Taktus project itself the channels are
Slack and the web app — this tenant's configuration, not a product name in the core — and the owner can
ask questions in either and is answered there.

## 2. How it is verified

- Every decision request, needs request and date the owner must act on produces the three renderings,
  and all three carry the same identifier, the same needed items and the same date. A test raises one
  of each kind and compares the three.
- The repository text holds only what future work needs. What the conversation was is not copied into
  the repository; a record may link to where it happened — the link, never the content (`CLAUDE.md`
  §9).
- The message is in the language the owner configured — for this tenant, German — and links to every
  file, issue and pull request it concerns.
- A report states what is needed, the steps to provide it, the work that stands still for want of it,
  and the date by which it is needed (ADR-0028). A report without one of the four is not sent.
- An answer in the channel is filed where it belongs only after Taktus reflected its interpretation
  back and the owner confirmed it (ADR-0008). An answer that cannot be read as one of the offered
  options is asked back, never acted on.
- Only an answer from the owner's identity, or from someone the owner named, is filed (UC-1.7). An
  answer from anyone else is acknowledged as not filed.
- Where a ticket system is configured, the report also goes there as a task, and closing the task
  without an answer files nothing.
- A message that cannot be delivered leaves the event in the repository and in the view, and the
  failed delivery is shown there.
- A failure Taktus notices about itself — an interface it depends on that stopped behaving as its
  adapter expects — reaches the owner through the same channel (DEC-0058).
- The owner can ask a question in the chat channel or in the web app and is answered in the place
  the question was asked, with only what the owner may see (UC-6.4).
- No message carries a secret value (`CLAUDE.md` §9).

## 3. Where the boundary lies

**Not a chat tool of Taktus's own.** The message goes into a tool the owner already uses (principle 1).
**Not the decision itself.** What is decided stays with the owner; the channel carries the question and
the answer. **Not the mechanism of the records.** What a decision request and a needs request contain is
ADR-0017 and ADR-0028; this use case renders and delivers them. **Not noticing the broken interface**,
which is the run's (issue #100); this use case delivers what was noticed.

## 4. What it rests on

Reports on request and on a schedule (UC-6.2), which this use case extends to the owner of a project;
needs requests and the status report (ADR-0028); decision requests in the repository (ADR-0017); the
interpretation of a free-text answer, reflected back and confirmed (ADR-0008); the ledger (ADR-0006);
channel identity (UC-1.7); the chat connector (issue #84). Stated by the owner outside the definition,
in conversation, as a requirement; `CLAUDE.md` §9 builds the channel on the rule that what concerned only
one person stays in the channel. The roadmap places it in `0.2.0` (#85).

**What an accepted decision supersedes in the owner's text.** The owner's text says that all three
renderings come *from the ledger*. The ledger holds no free text and no copy of a document; it holds
identifiers, tokens and digests (ADR-0006). The event is therefore a ledger entry, and its three
renderings are composed from the record that entry references — the decision request, the needs
request — not from the ledger alone.

## 5. What is proven so far

Built by ADR-0045 (issue #85) and proven by the named tests, against a recording carrier and
against the chat connector with the fake of its service. A decision request addressed to the
owner, a need, a date and a failure Taktus noticed about itself each become one report, and its
repository text, its message and its view carry the same identifier, the same items and the same
date. The repository text is English and names where an answer was given, never what was said.
The message is in the configured language — German for this tenant — and links every file, issue
and pull request the report names, the task and the view. A report without one of its four items,
or one that would carry a secret value, is not sent. An answer in the report's thread is read by a
rule, reflected without being quoted, and filed only once the same person confirmed it; one that
reads as no offered answer is asked back; one from anyone but the owner or someone the owner named
is acknowledged as not filed. A configured ticket system receives the report as a task, and closing
it files nothing. A message that cannot be delivered leaves the report in the view and in its
repository text with the failed delivery.

Not built: the owner's questions in the chat or the web app (UC-6.4, UC-1.5), the web app's page
(#105), raising a need or a date from a step of a process, and noticing a broken interface (#100),
which calls the failure entry built here. Against the real chat service nothing has run; that
waits for NEED-0018, and configuring the channel on the installed instance for NEED-0020.
