# ADR-0069 — A chat receives a level's text equivalent and a link to it live

**Status:** accepted · builds UC-6.10's condition *beyond the web app* (issue #193, DEC-0055);
answers the question ADR-0055 left to the first channel other than the web app

## Context
UC-6.10 §2 asks that a channel that can show a live representation receives it, and that a
channel that cannot receives the text equivalent and a link to the live representation.
ADR-0055 left open how a chat receives them: "decided where the first such channel is built".

Two kinds of reader exist today. The **web app** draws every level live (ADR-0063, ADR-0064).
A **channel** served by a connector carries messages: the repository channel and the chat
channel (`channel.repo`, `channel.chat`). Neither connector can show a moving picture. The
connector contract has no operation that could carry one; a message is text with links.

Four facts bound the answer.

- **Every level already carries its text equivalent.** Each element of a level has a `text`
  that names its method, class and state, what it waits on and what it used (ADR-0059,
  ADR-0063 §2). The web app is handed the same level.
- **The owner-facing channel exists** (ADR-0045, UC-6.11). It names the tenant's owner, the
  people the owner named, a conversation in a chat and a phrasebook in the owner's language. A
  message in a report's thread already comes back through the intake as an answer, not as a
  command.
- **The visibility predicate is one function** (ADR-0055 §5). Every read of a level asks it.
- **The repository is public** in the Taktus project, and may be in any tenant. Whoever reads
  an issue there is not a reader Taktus knows.

## Decision

### 1. The owner's conversation answers a request for a level
A message in the conversation of the owner-facing channel asks for a level when it is one of
the phrasebook's `show_run_words` followed by a run's identifier, or one of its
`show_process_words` followed by `<process>` or `<process>@<version>`. Nothing else is in the
message. The words are matched as the other words of a phrasebook are: case and the punctuation
around the message do not count. The identifier is taken as written.

The shipped phrasebooks say `show run` and `show process`, `zeige lauf` and `zeige prozess`.
A bare `run` was not chosen: "run P-01" reads as an instruction to start a process.

Such a message is answered in its own thread and is not a command. The intake hands it over
through the same port as an answer to a report (`ChannelAnswers`), with the roles the sender
holds. A message that is no such request goes on as before.

### 2. The answer is the level's own text, and the link to it live
The answer is the level the web app is handed, read through the same query
(`LevelQueries`), laid out as text: the first element's text, then one line for each further
element — each step and, at the process level, each run. Nothing is composed again; the
figures and the states are the level's.

The last line is the link to the level in the web app: `<view_base>/app/#/runs/<id>`, or
`<view_base>/app/#/processes/<id>/<version>`, as `web/src/lib/links.ts` builds the routes.
`view_base` is the control plane's address the channel already names for a report's view
(ADR-0045 §3). Without it, the answer carries the text and no link. The link names the level
and nothing else; the key stays where ADR-0063 §4 put it, in the reader's browser.

### 3. Only what its readers may see
The answer is read by whoever is in the conversation. The configuration knows those readers:
the owner, and the people the owner named. So:

1. A request is answered only in the configured conversation. A message at another address of
   the channel is not taken: who reads there is not known.
2. A request is answered only for the owner or someone the owner named. Anyone else is told
   the phrasebook's `not_shown`.
3. The level is read for the person who asked, by the one predicate. A run or a process they
   may not see is told `not_shown`, the same sentence as one that does not exist.
4. An answer that would carry a secret value the instance holds is not sent; `not_shown` is
   said instead (ADR-0045 §1).

A sender nobody could place is not answered here. The identity component offers them a link,
as for any other message (ADR-0040).

### 4. Which channels receive what
The web app is the one representation that shows a level live. No channel served by a
connector can, and each therefore receives the text and the link — today only the owner's
conversation. The repository channel receives neither: its readers are not known, and in a
public repository they are anyone.

### 5. A phrasebook either reads requests or does not
The four new entries of a phrasebook — `show_run_words`, `show_process_words`, `live` and
`not_shown` — are given all four or none. A phrasebook stored before this change has none; its
conversation reads no request until the channel is configured again.

### 6. Nothing is recorded
Showing a level is a read, as `GET /levels/…` is. It writes no ledger entry and stores
nothing. The reply has an idempotency key derived from the message, so a redelivery is
answered once.

## Alternatives
- **A picture of the level rendered for the chat.** Issue #193 excludes it, and a picture has
  no text a person who cannot see it could read.
- **A summary written for the chat.** It would be a second text equivalent beside the level's
  own. The two could disagree on a state or a figure, which UC-6.10's *the same figures as
  everywhere* forbids.
- **The text equivalent translated into the owner's language.** The level's text is composed in
  English inside `reporting`, and the web app shows it so. A translation would need every
  sentence of the levels in every phrasebook; the framing sentences are translated, the level's
  text is not.
- **The repository channel answers too.** Its readers are unknown, and in this project the
  repository is public.
- **Any identity of the tenant may ask.** The others in a shared conversation would then read
  what the asker may see, which may be more than they may.
- **A bare identifier as the request.** A message consisting of a run's identifier would be
  shorter. It would also take over messages meant as commands without any word saying so.

## Consequences
- `reporting` gains `ShowInChannelHandler` (`application/service/show_in_channel.py`), the
  reading rule `representation` and the rendering `shown` and `level_url`.
- `Phrasebook` gains four optional entries; the shipped German and English phrasebooks carry
  them.
- `ChannelAnswers.take` receives the roles of the identity as well (`ports/connector.py`).
- `owner_channel_wiring` takes the level queries; `taktusd` hands it the same ones the `api`
  role reads.
- The intake answers `shown` or `not_shown` for such a message.

## Where this promise ends
The answer is a snapshot taken when the request arrived. It does not move; the link is what
moves. Whether the link opens depends on the operator having configured the control plane's
address and having the web app in the image; Taktus cannot check either from the chat.

The predicate is asked for the person who asked. Until UC-6.4 narrows it by role, every reader
of the conversation sees what any identity of the tenant sees, so the answer is no wider than
the conversation. Once roles narrow it, the predicate must hold for every reader of the
conversation, which UC-6.4 adds; this change does not.

The level's text is English, as in the web app. Only the run and the process levels are
answered. The overview (ADR-0067) is drawn in the web app and not yet answered in a channel;
it and the origin of a result (#192) are answered once their words are added to the
phrasebooks, the same way.

The request is read as a whole message: "zeige lauf run_1 bitte" is not a request and goes on
as any other message. Where the chat's connector names no thread for a message, the answer is
said in the conversation itself. Against the real chat
service nothing has run: that waits for NEED-0018 and, on the installed instance, NEED-0020.
