# NTC-0107 — Both connectors read a member list

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-10
**Raised in:** [#173](https://github.com/Jersyfi/taktus/pull/173)

## 1. What was decided

Each of Taktus's two connectors gains one operation that reads the platform's member list, and
changes nothing outside.

- **`chat.members.list`**, capability `chat.members`, on the chat connector: every member of the
  workspace, as its account identifier, display name, person or automation, active or
  deactivated, and its address with whether the service confirmed it. The address is empty
  where the app may not read addresses.
- **`repository.members.list`**, capability `repository.members`, on the repository connector:
  every collaborator of the repository, as its account number, login name, person or
  automation, and role.

Nothing else of a member is passed on: no presence, time zone, title or picture. Nothing calls
either operation yet. They exist so that DEC-0127 — whether an administrator may link accounts
from such a list — rests on what the platforms actually yield, and so that the live tests show
it on the real services. An account is named as the intake names a sender, so that a member and
a link refer to the same account.

## 2. The evidence

- The owner's direction of 2026-10-10 (NEED-0017, NEED-0020) asks that linking from a member
  list be proven technically against the platforms Taktus uses.
- The chat service's `users.list` needs the app's `users:read`; the address needs
  `users:read.email`, and `is_email_confirmed` says whether the service confirmed it. The fake
  of the chat service answers in that shape and refuses without the first permission
  (`tests/fakes/chat_service.py`).
- The repository service's collaborator list needs "metadata: read", which Taktus's app holds
  (NEED-0013). Read on this repository on 2026-10-10 with a user token, it answered number,
  login, kind and role, and no address. The fake answers the same
  (`tests/fakes/repository_service.py`).
- `tests/adapters/connectors/test_member_lists.py` shows both operations against the fakes: the
  fields, a list longer than a page, a missing permission as `forbidden`, a list without
  addresses, and that only an active person's confirmed address could suggest a link. The live
  tests (`test_chat_live.py`, `test_repository_live.py`) assert the same on the real services
  by counts alone, so that no member reaches a public log.

## 3. What was considered

- **Prove it in the test with the services' raw interfaces, without an operation.** It would
  prove the services and not Taktus: what an identity component could read is what a connector
  declares.
- **Pass the member object on as the service answers it.** It carries presence, time zone, title
  and more. Principle 14 and data protection (principle 11) say pass on only what linking
  needs.
- **Wait for the answer to DEC-0127.** The answer is better when it rests on what the platforms
  yield, and the live run on the chat service is the first run after the app is installed.

## 4. Which entry permits it

M2.4: "A change of what the software does, made inside an agreed scope, that breaks no contract,
moves no limit or autonomy level and says nothing public." The scope is the owner's direction to
prove linking technically. Adding an operation to a connector's own declaration breaks no
contract: the connector contract leaves each connector's operations to its declaration. The
operations only read, and no process calls them. What a use case requires is untouched; that is
DEC-0127 (M3.15).
