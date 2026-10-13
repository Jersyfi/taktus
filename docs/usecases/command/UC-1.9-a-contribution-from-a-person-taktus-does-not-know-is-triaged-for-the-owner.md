---
id: UC-1.9
title: A contribution from a person Taktus does not know is triaged for the owner
component: command
epic: E1
serves: [P4, P11, P14]
state: building
version: 0.3.0
tests: [tests/composition/test_contributions.py::test_an_issue_an_unknown_sender_opens_starts_the_triage_for_its_owner, tests/composition/test_contributions.py::test_a_pull_request_from_outside_starts_the_triage_too, tests/composition/test_contributions.py::test_a_contribution_delivered_twice_starts_the_triage_once, tests/composition/test_contributions.py::test_a_contribution_is_never_completed_into_a_command_of_its_sender, tests/components/run/test_triage_rules.py::test_spam_is_what_a_pattern_finds_case_blind_and_nothing_else, tests/components/run/test_triage_rules.py::test_a_defect_or_a_feature_names_a_planned_version_and_a_summary, tests/integration/test_triage.py::test_spam_is_closed_with_its_reason_and_nobody_is_asked, tests/integration/test_triage.py::test_a_feature_approved_by_the_owner_stays_open_in_its_version, tests/integration/test_triage.py::test_a_declined_pull_request_is_closed_with_the_owner_s_words_and_never_merged, tests/integration/test_triage.py::test_the_ledger_never_names_the_sender, tests/governance/test_process_asks.py::test_a_step_that_asks_is_asked_at_every_level]
adrs: {ADR-0012: 2116f271375d, ADR-0040: 9d4e8c625856, ADR-0042: bfc76a4a3797, ADR-0048: 46ce91536fd5, ADR-0088: 655238bb8152}
supersedes: null
---

# UC-1.9 — A contribution from a person Taktus does not know is triaged for the owner

## 1. What must be achieved

A public channel is one anybody can write in, such as the issues and pull requests of a public
repository. People Taktus does not know contribute there: they report a problem, propose a
feature, open a pull request, or send spam. A **contribution** is such an issue or pull request,
opened by a sender the identity component cannot place (UC-1.7).

A contribution starts a **triage process** of the organisation's own. The person does not have to
register. The process acts for its owner: the identity that made the process's version active.
The person who wrote the contribution is data of the process. They are never its actor, and
the process gives them no right.

The process classifies the contribution as a defect, as a feature together with the version it
would belong to, or as spam. It prepares a defect or a feature for the owner and asks the
owner's approval. What the owner approves stays open and enters the backlog. What the owner
declines is closed, with the reason. Spam is closed without asking anybody.

Blocking a sender is an act on a person, and it stays with a person. An outside pull request is
triaged and held: the process never merges it. The repository's contributing guide carries a
notice about how an outside person's public data is processed. The session drafts it; its
wording is the owner's.

## 2. How it is verified

- An issue or a pull request opened on a public channel by a sender the identity component cannot
  place starts one run of the triage process. The same contribution delivered twice, or reacted to
  by two instances, starts it once.
- Whether the run starts is decided by a rule over the event and the identity component's answer.
  No language model or other probabilistic method decides it.
- The run acts for the identity that made the triage process's version active. The sender gains
  no identity, no link, no right and no command from it. Their account is read as part of the
  contribution and never written to the ledger.
- Every contribution the run classifies receives exactly one class: `defect`, `feature` or
  `spam`. A `feature` names the planned version it would belong to.
- A contribution classified `spam` is closed in the channel with the reason, without a person
  being asked.
- A `defect` or a `feature` is put to the owner as a decision request (UC-7.4). It names the
  class, what the contribution asks for, and, for a feature, the proposed version. While the
  request is open, the contribution is neither closed nor placed in the backlog.
- What the owner approves stays open and is placed in the backlog: a feature in the version the
  owner approved. What the owner declines is closed in the channel with the owner's reason.
- The process never blocks a sender, at any autonomy level. Where a sender should be blocked, a
  person does it.
- The process never merges a pull request it triaged, whatever the owner's answer. An approved
  outside pull request stays open and unmerged.
- Every outward act of the run — a comment, a label, a closing — is an entry in the ledger, and
  its class is in the provenance record of the step that produced it.
- No metric, report or ledger entry counts or assesses the contributions of one sender.
- The repository's contributing guide carries a notice: which public data of an outside person
  the triage processes, for what purpose, and that the person never becomes an actor. Its wording
  is the owner's.

## 3. Where the boundary lies

**Not registration.** The person creates no account, links nothing and is asked for no consent;
they never act, so no identity is needed. Linking an account stays UC-1.7. **Not every message.**
A comment by an unknown sender on an existing issue is no contribution; it is answered as UC-1.7
says. **Not a placed sender.** An issue opened by a person Taktus knows starts what UC-4.14 says,
acting for that person; no process trigger is ever matched by an unknown sender's event, and that
rule of UC-4.14 stands. The triage is the one process an unknown sender's contribution starts,
and it acts for its owner. **Not a private channel.** A channel only known people can write in
has no contribution in this sense. **Not accepting outside code.** Whether outside code may be
merged is the licence's question (ADR-0012); in this repository nothing from outside is merged
while the licence is open (DEC-0044). **Not blocking.** Blocking is a person's act; the process may
propose it and does nothing more. **Not the notice's wording.** It is published under the
project's name and is the owner's (M3.7). **Not an assessment of people.** The process judges a
contribution, never the person who wrote it.

## 4. What it rests on

The owner's answer to DEC-0175, Option A, of 2026-10-11, and the direction recorded with DEC-0127.
UC-1.7, for who is unknown and how an unknown sender is otherwise answered; UC-4.14, for how an
event starts a process; UC-7.4, the decision request. ADR-0040 and ADR-0048 state today that an
unknown sender's event is kept nowhere and starts nothing; building this use case changes that
for a contribution on a public channel. ADR-0042 holds a run at an anchor; ADR-0012 and DEC-0044
the licence. Issue #245 builds it, in the roadmap's `0.3.0`. Not in the definition: written from the
owner's direction, numbered as the next free number of area 1.

## 5. What is proven so far

Built by #245 (ADR-0088): a contribution an unknown sender opens on a public channel starts the
triage once, acting for its owner, and is never completed into a command of the sender; spam is
found by a rule first and closed unasked; a defect or a feature names its version and is put to
the owner; what is approved stays open in its version and what is declined is closed with the
owner's words, never merged; the ledger never names the sender — by the named tests, against a
fake repository service. Not yet: the notice in the contributing guide, whose wording waits for
the owner (DEC-0181), and so the triage is not switched on for this repository.
