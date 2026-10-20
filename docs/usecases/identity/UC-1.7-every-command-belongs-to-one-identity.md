---
id: UC-1.7
title: Every command belongs to one identity
component: identity
epic: E1
serves: [P4, P12]
state: built
version: 0.2.0
tests: [tests/integration/test_first_slice.py::test_nothing_executes_without_an_identity, tests/components/command/test_complete_intake.py::test_an_unknown_sender_is_kept_nowhere_and_completed_never, tests/components/identity/test_directory.py::test_one_account_maps_to_at_most_one_identity_and_one_identity_to_many, tests/components/identity/test_directory.py::test_a_code_from_the_persons_account_written_from_the_account_links_it, tests/components/identity/test_directory.py::test_a_matching_name_or_address_links_nothing, tests/components/identity/test_directory.py::test_the_organisations_identity_source_links_what_it_answers, tests/components/identity/test_directory.py::test_every_link_and_every_removal_is_a_ledger_entry_and_revoked_is_unknown, tests/components/command/test_complete_intake.py::test_identity_and_path_are_the_components_never_the_connectors, tests/components/command/test_complete_intake.py::test_several_events_within_the_window_get_one_offer_and_a_later_one_another, tests/components/command/test_complete_intake.py::test_an_event_without_the_senders_text_is_never_answered_nor_read_for_a_code, tests/adapters/connectors/test_repository_unknown_sender.py::test_an_issue_opened_and_labelled_together_gets_one_offer, tests/adapters/connectors/test_repository_unknown_sender.py::test_a_label_added_alone_is_answered_nothing, tests/adapters/connectors/test_repository_unknown_sender.py::test_after_the_window_a_comment_is_offered_again]
adrs: {ADR-0020: e94e1924e1ec, ADR-0024: 52ba89e4adec, ADR-0033: eb18bea6bfb4, ADR-0040: 9d4e8c625856}
supersedes: null
---

# UC-1.7 — Every command belongs to one identity

## 1. What must be achieved

A sender in a command channel — a ticket system, a knowledge tool, a team chat, a messenger — is
mapped to exactly one authenticated Taktus identity. That identity carries the sender's rights,
their place in the organisation's structure, and where their cost is attributed. The mapping is
made once: by linking the channel account in the person's Taktus account, or through the
organisation's own identity source. A sender Taktus does not know gets a question or an offer to
register, never an execution.

## 2. How it is verified

- No command is executed without an identity.
- An event from an unknown sender becomes no command and is kept nowhere as one. The sender
  receives, in the channel, a question or an offer to register.
- One channel account maps to at most one identity; a second link for it is refused. One identity
  may hold accounts on many channels.
- A link is made only by the person confirming it in their Taktus account, or by the
  organisation's identity source. It is never inferred from a matching name or address.
- Every link and every removal of a link is a ledger entry. An administrator sees every link of the
  tenant and can revoke one; the next event from a revoked account is treated as from an unknown
  sender.
- The identity and the organisational path of a command are set by the identity component, never by
  the connector that received the event (`control-plane.md` §2).
- A channel where Taktus rolls out an assistant (UC-12.1) is not a command channel and does not
  follow this rule.

## 3. Where the boundary lies

**Not authorisation.** What an identity may do is UC-7.3; this use case establishes who it is.
**Not Taktus's own identity** towards a service: what Taktus does on its own behalf, it does as an
identity of its own (ADR-0033). **Not channel security.** That an event is genuine is the
connector's intake, which verifies the signature first (ADR-0024).

## 4. What it rests on

The command and the identity port of `docs/architecture/control-plane.md` §2; the intake half of the
connector contract (ADR-0024); tenants (ADR-0020); the ledger (UC-6.1); the provisional identity it
replaces (DEC-0013). An issue or pull request an unknown sender opens on a public channel is
also triaged for the organisation, with the sender as data only: UC-1.9 (DEC-0175). Definition `UC-1.7`, new in version 2. The identity component is on the roadmap's
`0.2.0` (#82), hence the version.

## 5. What is proven so far

The identity component answers every resolution; the provisional identity of DEC-0013 is removed
(NTC-0080). By the named tests:

- The command line executes nothing without an identity, nor with one the tenant does not know.
- An unknown sender's event is kept nowhere and becomes no command; a person is answered in the
  channel with the offer to link the account. An event placed before its link was revoked is
  completed into no command.
- Several events of one unknown person in one conversation, delivered together, get one offer
  there, against the repository connector and its fake service; after the configured window a
  new event is offered again. An event that carries no text the person wrote — a label added —
  is answered nothing, and a code in the issue's text links nobody (ADR-0040, amended; issue
  #247).
- One channel account is linked to at most one identity, and a second link for it is refused; one
  identity holds accounts on two channels.
- A link is made by a code from the person's Taktus account written in the channel from the
  account, or by what the organisation's identity source answers. A matching name or address
  links nothing.
- Every link and every revocation is a ledger entry, without the account. The tenant's links are
  listed with the revoked ones, and an administrator revokes one; a revoked account is from an
  unknown sender again.
- A command's identity and organisational path come from the link, even where the connector's
  context names others.

That a channel where Taktus rolls out an assistant follows no command rule is not tested; that
channel (UC-12.1) is not built.
