# NTC-0080 — The identity component replaces the provisional identity

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-09
**Raised in:** the pull request for issue #82

## 1. What was decided

Who a command acts for now comes from the identity component, and from nothing else
(ADR-0040, UC-1.7).

- **Old:** one configured operator identity per tenant, `TAKTUS_PROVISIONAL_IDENTITY`, answered
  every resolution (DEC-0013). Every sender of every channel became the tenant's operator. A
  webhook delivery was kept in the one configured tenant and completed as the operator. The
  command line took the operator when `--identity` was not given, and accepted any label as an
  identity.
- **New:** a sender is placed by the link of their account. A person makes the link: with their
  account key they create a single-use code in their Taktus account (`POST
  /identity/link-codes`) and write it in the channel from the account. The organisation's
  identity source, behind a port of its own, may make it too. An unknown sender's event is kept
  nowhere; the sender is answered in the channel, through the reply operation the channel's
  connector declares, as Taktus itself. An administrator adds identities and sees and revokes
  links with `taktusctl identity`. Every link, revocation, addition and new key is a ledger
  entry. The command line names an identity the tenant knows (`--identity` or
  `TAKTUS_IDENTITY`), and the component supplies its organisational path.
- The variable, the provisional adapter and the field `provisional` are gone from the code, the
  configuration and the documentation. The reference connector declares `channel.repo.reply`.
  Migration 0015 adds the tables.

## 2. The evidence

- `tests/components/identity/test_directory.py`: a code from the person's account written from
  the account links it; a matching name or address links nothing; a code links once, only in
  time and only on its channel; a second link for an account is refused in any tenant, and one
  identity holds accounts on two channels; every link and revocation is a ledger entry without
  the account, and a revoked account is unknown again; the identity source's answer becomes a
  link; a new key retires the old.
- `tests/components/command/test_complete_intake.py`: `test_an_unknown_sender_is_kept_nowhere_
  and_completed_never` holds without the provisional adapter, and the sender is answered in the
  channel; a message with a code links the account and is no command; the identity and path
  come from the link even when the connector's context names others.
- `tests/integration/test_first_slice.py::test_nothing_executes_without_an_identity` stays
  green, now also for an identity the tenant does not know.
- `tests/adapters/rest/test_surface.py`: the link-code route refuses without a valid key; the
  intake answers an unknown sender and keeps nothing.
- `git grep TAKTUS_PROVISIONAL_IDENTITY` finds the variable only in records of what was.

## 3. What was considered

- **Keep the provisional identity as a fallback.** DEC-0013 refused that in advance: a fallback
  acting as the operator is the hole UC-1.7 closes.
- **Accept any `--identity` label on the command line, as before.** A command would then carry
  an identity the component does not know and an organisational path nobody set. Naming a known
  identity costs one `taktusctl identity add` per instance.
- **Show the code to the unknown sender and let a person confirm it in their account.** On a
  public channel the first person to confirm a code they read would own the link (ADR-0040).

## 4. Which entry permits it

M2.4: "A change of what the software does, made inside an agreed scope, that breaks no contract,
moves no limit or autonomy level and says nothing public." The scope is UC-1.7 and issue #82 in
`0.2.0`. The connector contract gains an optional operation and loses nothing, so no published
contract breaks (M3.5); no limit or level moves; the answer to an unknown sender is the product
doing what UC-1.7 requires, not a statement under the project's name (M3.7).
