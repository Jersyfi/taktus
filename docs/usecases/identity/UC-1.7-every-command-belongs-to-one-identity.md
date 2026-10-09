---
id: UC-1.7
title: Every command belongs to one identity
component: identity
epic: E1
serves: [P4, P12]
state: built
version: 0.2.0
tests: [tests/integration/test_first_slice.py::test_nothing_executes_without_an_identity, tests/components/command/test_complete_intake.py::test_an_unknown_sender_is_kept_nowhere_and_completed_never, tests/components/identity/test_directory.py::test_one_account_maps_to_at_most_one_identity_and_one_identity_to_many, tests/components/identity/test_directory.py::test_a_code_from_the_persons_account_written_from_the_account_links_it, tests/components/identity/test_directory.py::test_a_matching_name_or_address_links_nothing, tests/components/identity/test_directory.py::test_the_organisations_identity_source_links_what_it_answers, tests/components/identity/test_directory.py::test_every_link_and_every_removal_is_a_ledger_entry_and_revoked_is_unknown, tests/components/command/test_complete_intake.py::test_identity_and_path_are_the_components_never_the_connectors]
adrs: {ADR-0020: 406f1ca33b50, ADR-0024: d57aa05c4f28, ADR-0033: eb18bea6bfb4, ADR-0040: af5a6cdb5889}
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

**Proven so far:** nothing executes without an identity, and an unknown sender's event is completed
into no command, by the named tests. Every resolution is still answered by the provisional operator
identity of DEC-0013: one configured identity per tenant. Linking, the organisation's identity
source, the question to an unknown sender and revocation are not built.

## 3. Where the boundary lies

**Not authorisation.** What an identity may do is UC-7.3; this use case establishes who it is.
**Not Taktus's own identity** towards a service: what Taktus does on its own behalf, it does as an
identity of its own (ADR-0033). **Not channel security.** That an event is genuine is the
connector's intake, which verifies the signature first (ADR-0024).

## 4. What it rests on

The command and the identity port of `docs/architecture/control-plane.md` §2; the intake half of the
connector contract (ADR-0024); tenants (ADR-0020); the ledger (UC-6.1); the provisional identity it
replaces (DEC-0013). Definition `UC-1.7`, new in version 2. The identity component is on the roadmap's
`0.2.0` (#82), hence the version.
