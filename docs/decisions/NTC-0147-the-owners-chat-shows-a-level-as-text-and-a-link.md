# NTC-0147 — The owner's chat shows a level as text and a link

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-10
**Raised in:** issue [#193](https://github.com/Jersyfi/taktus/issues/193), in the pull request that closes it

## 1. What was decided

UC-6.10's condition *beyond the web app* is built as ADR-0069 decides. What the software does
differently:

- A message in the conversation of the owner-facing channel that reads `show run <run>` or
  `show process <process>[@<version>]` — `zeige lauf`, `zeige prozess` in German — is answered
  in its thread. The answer is the run level or the process level as the web app is handed it,
  as text: every element's text equivalent, one line each. Its last line links the level in the
  web app, under the control plane's address the channel names. The message is not kept as an
  intake event and does not become a command; the intake answers `shown`.
- Anyone but the owner or someone the owner named, a run or a process the asker may not see, one
  that does not exist, and an answer that would carry a secret value are all told the same
  sentence; the intake answers `not_shown`.
- A message at another address of the chat channel, a sender nobody could place, and any other
  message go on as before.
- The shipped phrasebooks gain four entries: `show_run_words`, `show_process_words`, `live`,
  `not_shown`. A phrasebook names all four or none. A channel configured before this change
  reads no request until it is configured again.
- `ChannelAnswers.take` receives the sender's roles as well.

## 2. The evidence

- Issue #193, its sections "How it is verified" and "Where the boundary lies"; UC-6.10 §2
  *beyond the web app*; ADR-0045; ADR-0055 *Where this promise ends*; ADR-0063; ADR-0064;
  DEC-0055.
- `tests/adapters/connectors/test_owner_channel_chat.py::test_a_run_asked_for_in_the_chat_is_answered_with_its_text_and_a_link_to_it_live`:
  through the chat connector and the fake of its service, the owner's request is answered with
  the run level's text, element by element, and the link; an outsider's with the one sentence;
  no intake event is kept.
- `tests/adapters/rest/test_levels_in_a_channel.py`: the text the chat receives is the text of
  `GET /levels/runs/{id}` — the same states and figures — and the link carries the instance's
  prefix; a run of another tenant is answered as a missing one.
- `tests/components/reporting/test_levels_in_a_channel.py`: the process level, the people
  answered, a secret withheld, the address, the reading rule, the phrasebook's four entries, the
  web app's routes.

## 3. What was considered

- **Answer in the repository channel too.** Rejected: its readers are not known, and this
  project's repository is public (ADR-0069 §4).
- **Answer any identity of the tenant.** Rejected: the others in the conversation would read
  what the asker may see.
- **Fill the four entries into stored phrasebooks by a migration.** Rejected: a migration
  would write sentences in a language into the database, and a tenant's own phrasebook has no
  shipped sentence to fall back on. Configuring the channel again takes the shipped one.
- **Record each answer in the ledger.** Rejected: showing a level is a read, and `GET /levels/…`
  records none.

## 4. Which entry permits it

M2.4, *"A change of what the software does, made inside an agreed scope, that breaks no
contract, moves no limit or autonomy level and says nothing public."* The scope is issue #193
under UC-6.10, accepted in DEC-0055, and ADR-0069. No contract under `contracts/` changes: the
port `ChannelAnswers` is internal, and the phrasebook's new entries are optional. No limit or
level moves. Nothing is said publicly: the answer goes only to the owner's conversation.
