# NTC-0096 — The owner channel's open readings, strictly

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-09
**Raised in:** [#165](https://github.com/Jersyfi/taktus/pull/165), for issue #85
**How it follows:** UC-6.11 §2 states what must hold and leaves six readings open. Each is decided by the source that governs the same question elsewhere: the repository rule of CLAUDE.md §9 (English; the link, never the content), ADR-0008 and ADR-0042 (an answer read by a rule, nothing acted on before it is confirmed, the person whose answer was read confirms it), UC-1.7 (only a placed identity acts), ADR-0015 (no time of a named person shown to others) and principle 1 (no tool of Taktus's own). Where two readings were both consistent, the one taken is the stricter in substance — fewer answers read, fewer people named, nothing written outside the product — and the one with less ceremony: no new message kind, no new store.

## 1. What was decided

1. **The repository text** is the English record the control plane keeps and serves, and the
   body of the task in a ticket system. Taktus does not commit it into a repository: writing into
   a tenant's repository is an act of its own, not this channel's, and UC-6.11 asks for the
   rendering, not the commit.
2. **The words an answer is read by** are the phrasebook's, and a message is read only when it is
   one of them as a whole: "ja" confirms, "ja, passt" is asked back. A decision's answer is read
   by the decision component's own rule (ADR-0042 §4).
3. **Only the person whose answer was read confirms it.** A confirmation word from anyone else
   is no confirmation; it is read as an answer of its own, and asked back.
4. **A sender nobody could place who writes in a report's thread** is told that the answer is not
   filed, and is not offered how to link an account there: the thread belongs to the owner, and
   the offer stays where a sender writes to Taktus on their own.
5. **The view names nobody.** Its history says whether the reader acted, not who did.
6. **Whom the owner named is configuration**, written by whoever configures the channel, and
   only the tenant's owner and those identities read the reports.

## 2. The evidence

- UC-6.11 §2: "only an answer from the owner's identity, or from someone the owner named, is
  filed"; "an answer that cannot be read as one of the offered options is asked back, never acted
  on"; "the repository text holds only what future work needs".
- ADR-0042 §4 and §6: every answer is reflected and confirmed by the person who gave it; a request
  shown to a decider who did not answer it names no answerer.
- CLAUDE.md §9: "A repository record may link to where a conversation happened — the link, never
  the content."
- `tests/components/reporting/test_owner_channel.py` holds each reading.

## 3. What was considered

- **Committing the repository text through the repository connector.** Rejected for this
  channel: the connector has no operation that writes a file, and writing into a tenant's
  repository would be a process's act with its own anchor, not a side effect of a report.
- **Reading "ja" anywhere in a message.** Rejected: "ja, aber nicht so" would be filed. A reading
  that is wrong in a way the person sees is the rule's limit; one that files the opposite is not.
- **Letting the owner confirm a named person's reading.** Rejected: ADR-0042 keeps confirmation
  with the person whose words were read.
- **Offering an unknown sender the link in the thread.** Rejected: the owner's thread would carry
  an offer to whoever wrote there.

## 4. Which entry permits it

None of modes 3 and 4 names how the owner-facing channel reads an answer, whom it shows a view or
what its repository text is; what UC-6.11 requires is unchanged (M3.15), and no limit or level
moves. No entry of mode 2 names it. M2.6 applies: decided in the direction of the sources above.

## 5. The entry it proposes

**M1.17** — *Reading in the owner-facing channel*: how an answer in the owner's channel is read,
confirmed and shown follows ADR-0042's rule for a decision request — a whole-message rule, the
same person confirms, no one named in a view — and a new kind of answer is read the same way.
Mode 1, because it applies an accepted ADR's rule to a new channel without choosing anything new.
