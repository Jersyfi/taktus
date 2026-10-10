# NTC-0148 — The owner's chat shows the overview as text and a link

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-10
**Raised in:** issue [#204](https://github.com/Jersyfi/taktus/issues/204), in the pull request that closes it

## 1. What was decided

The overview of UC-6.10 is answered in the owner's conversation as ADR-0069 answers a run and a
process. What the software does differently:

- A message in the conversation of the owner-facing channel that reads `show overview` —
  `zeige überblick` in German — and nothing else is answered in its thread. Case, spaces and the
  punctuation around the words do not count, as for every other word of a phrasebook.
- The answer is the overview as the web app is handed it, as text, in the order the web app
  writes its own text equivalent: each area's text, then one line for each process of it and
  for each step running in that process. The last line links the web app's root route,
  `<view_base>/app/#/`, where the overview is drawn live.
- Who is answered, and what they are told otherwise, is unchanged from NTC-0147: the owner and
  whom the owner named are shown the overview as they may see it; anyone else, and an answer
  that would carry a secret value, are told `not_shown`. The intake answers `shown` or
  `not_shown`, keeps no intake event and writes no ledger entry.
- A phrasebook gains a fifth optional entry, `show_overview_words`. It is given only together
  with the four entries of ADR-0069 §5. A phrasebook that has the four and not the fifth stays
  valid and reads no request for the overview until the channel is configured again. No word
  may ask for two levels.

## 2. The evidence

- Issue #204, its sections "How it is verified" and "Where the boundary lies"; UC-6.10 §2
  *beyond the web app*; ADR-0067; ADR-0069 and its amendment of this date.
- `tests/adapters/connectors/test_owner_channel_chat.py::test_the_overview_asked_for_in_the_chat_is_answered_with_its_text_and_a_link_to_it_live`:
  through the chat connector and the fake of its service, the owner's request is answered with
  every element's text of the overview and the link; an outsider's with the one sentence; no
  intake event is kept.
- `tests/adapters/rest/test_levels_in_a_channel.py::test_the_owner_s_chat_receives_the_overview_s_text_and_a_link_to_it_live`:
  the text the chat receives is the text of `GET /levels/overview` over HTTP, line for line,
  with the same counts; another tenant's run is neither drawn nor counted.
- `tests/components/reporting/test_levels_in_a_channel.py`: the order of the lines, the people
  answered, a secret withheld, the reading rule, the fifth entry and both shipped phrasebooks.

## 3. What was considered

- **The five entries all or none**, as the plan of the session that built #193 had it.
  Rejected: a phrasebook stored after #193 has the four entries, and a rule of five would make
  that stored channel unreadable — the owner's channel would stop until someone configured it
  again. Requiring the fifth only with the other four keeps the rule's purpose — no request is
  read without the sentences to answer it — and breaks nothing stored.
- **A bare `overview`** as the words. Rejected for the reason ADR-0069 §1 gives for a bare
  `run`: a single word takes over messages meant otherwise.
- **The overview's areas only, without the processes.** Rejected: the issue asks for every
  element's text of the level, and the web app writes them all.

## 4. Which entry permits it

M2.4, *"A change of what the software does, made inside an agreed scope, that breaks no
contract, moves no limit or autonomy level and says nothing public."* The scope is issue #204
under UC-6.10, accepted in DEC-0055, and ADR-0069, whose *Where this promise ends* named this
step. No contract under `contracts/` changes: the phrasebook's new entry is optional. No limit
or level moves. Nothing is said publicly: the answer goes only to the owner's conversation.
