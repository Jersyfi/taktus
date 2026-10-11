# NTC-0191 — An unknown sender is answered once per window

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-11
**Raised in:** the pull request that closes issue #247

## 1. What was decided

An *unknown sender* is a person whose account on a channel is linked to no Taktus identity.
Taktus answers such a person in the channel with an *offer*: how to link the account
(ADR-0040 §5). Until now every event of theirs led to an offer, and the offer was meant to be
said once per conversation. Three things change.

- **An event that carries no text the sender wrote is not answered.** The connector says so in
  a new optional field of its intake, `intent.authored` (`contracts/connector/v1` §7). The
  repository connector sets it to `false` for a label added, a pipeline run and a push. Such an
  event is not answered, its text is not read for a link code, and it is not handed to the
  owner-facing channel as an answer. It is still kept nowhere.
- **One offer answers a window.** Several events of one person in one conversation within the
  window get one offer there. A later event may get another. The window is configured by
  `TAKTUS_OFFER_WINDOW_SECONDS`, a day by default. The offer's idempotency key now carries the
  stretch of the window the offer falls in, so that a later offer is a new comment and not a
  replay of the first.
- **The offers of one conversation are made one at a time.** An instance makes the offer of a
  conversation under a lock of that conversation. Deliveries that arrive together wait for
  each other.

ADR-0040 is amended to say the same (M1.9).

## 2. The evidence

- **What happened on the instance.** Issue #247 was opened at 17:17:28 and received three labels
  at 17:17:30, three deliveries of `issues.labeled`. At 17:17:31 three offers were posted on it,
  each with the same idempotency mark (`gh api repos/Jersyfi/taktus/issues/247/comments`). The
  label `in-progress` added at 17:53:36 got no offer: one delivery alone found the earlier
  offer by its mark. The triple is therefore not one event processed three times. It is three
  label events, each answered, whose lookups of the earlier offer ran at the same moment. Each
  found none, and each posted. The connector's lookup and its write are two requests, and
  nothing kept two calls with one key apart.
- **A label is answered with somebody else's text.** The repository connector normalises a label
  added with the issue's title and body as its text (`intake.py`, `issue.labelled`). The intake
  handed that text to the identity component, which looks for a link code in it. A code in an
  issue's body, written by its linked author, would have linked the account of whoever labelled
  the issue next.
- **The owner's statement of the requirement.** Issue #247, opened by the owner: "An event that
  carries no text the sender wrote — a label set, an assignment — is never answered", and
  several events within a configurable window lead to one reply.
- **Tests.** `tests/adapters/connectors/test_repository_unknown_sender.py` delivers an issue
  opened, three labels and a comment at once through the repository connector to its fake
  service: one offer lands on the issue. With the lock removed, the same test finds two. A label
  added alone is answered nothing; after the window a comment is offered again.
  `tests/components/command/test_complete_intake.py` shows the window, the lock and the label
  without the connector. `tests/adapters/connectors/test_repository_intake.py` shows which kinds
  carry `authored: false`.

## 3. What was considered

- **Keep the window in the database.** It would hold across instances and restarts exactly. It
  is a new aggregate and a migration for a reply. It would also be a row about a person Taktus
  does not know, which ADR-0040 keeps nowhere. The key's stretch covers redeliveries, restarts
  and other instances within a stretch, and ADR-0040 states where that ends.
- **A key per stretch, without memory.** Two events either side of a stretch's end would each be
  offered, however close together. The memory of the instance closes that within one instance.
- **Decide by the event's kind in the core.** The core would have to know which kinds carry
  whose text, and a kind outside the catalogue would have no answer. The connector reads the
  event and knows. The field is optional, so a connector that says nothing behaves as before.
- **Answer a label, once per window, like any event.** The issue rules it out, and the code
  search in somebody else's text is a fault of its own.

## 4. Which entry permits it

M2.4 of `docs/decisions/anchors.taktus.md`: "A change of what the software does, made inside an
agreed scope, that breaks no contract, moves no limit or autonomy level and says nothing public."
The scope is issue #247, in `0.2.0`. The connector contract gains an optional field, which
breaks no connector and no intake that exists. No limit or level moves, and Taktus says less in
public than before. UC-1.7 §2's offer to an unknown sender is read, as the issue reads it, as
the answer to what the sender wrote; its sections 1 to 3 are unchanged.
