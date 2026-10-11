# NTC-0193 — The wiki keeps the mark and the digest of what Taktus wrote in a page's tags

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-11
**Raised in:** the pull request for issue #197

## 1. What was decided

Until now the capability `knowledge.pages` was served only by the directory connector. A
connector to the wiki the owner chose (DEC-0176, NEED-0021) now serves it too
(`src/taktus/adapters/driven/connectors/bookstack/`). ADR-0065 §4 states the operations. These
are the choices it left open:

1. **The mark, the key and two digests go into the page's tags.** The wiki keeps a list of
   tags on every page and returns them unchanged. A write puts there the idempotency key, the
   mark, the digest of the text written, and the digest of the text as the wiki stored it. The
   key and the mark are split into numbered parts of URL-safe base64, because a tag's value is
   short and may be trimmed. A person's own tags stay.
2. **A wiki that changes the text it stores does not make a page look edited.** The connector
   reads the stored text back from the wiki's answer to the write. Where it differs, it writes
   the tags once more with the digest of the stored text. A page whose text still hashes to that
   digest reads with the digest of what was written. Any other text reads with its own digest,
   and the mark stays, so the page is `edited`. This is what ADR-0065's bound asked #197 to show.
3. **A place is shelf, book, page.** A list takes one to three names, a read and a write
   exactly three. A place the wiki cannot hold is refused as `invalid` before any request. A name
   that matches twice ends `conflict`. A page inside a chapter has no place and is left alone. A
   write into a shelf or book that does not exist ends `not_found`: a person makes them.
4. **The credential is read from its file alone.** The contract allows a value in the
   environment; this connector reads `TAKTUS_CREDENTIAL_KNOWLEDGE_TOKEN_FILE` and nothing else,
   as the issue asks.
5. **S-05 names the credential.** Its steps `read-held` and `publish` now reference
   `KNOWLEDGE_TOKEN`, so that a wiki's connector can act; the directory ignores it. The bundle
   becomes version 2.
6. **The live test writes into a scratch book on a shelf of its own**, `Taktus live test` /
   `Live test`, so that the guides' shelf holds the guides alone. NEED-0021 now asks for that
   shelf and book, for the role's rights on it, for the secrets of the environment `live`, and for
   the declaration `KNOWLEDGE_TOKEN: none` where an instance names its platform (M2.5). The
   wiki's address is a secret of that environment, not a variable, so that the public log masks
   it.

What changes for an operator: one more connector to deploy where the guides go to the wiki,
one entry of `TAKTUS_CONNECTORS`, and the credential `KNOWLEDGE_TOKEN` (`CREDENTIALS.md`).
Without it nothing changes: the guides go to the directory the instance serves, and nowhere
otherwise.

## 2. The evidence

- `tests/adapters/connectors/test_knowledge_wiki.py`, against a fake of the wiki that changes
  the text it stores: an untouched page reads with the digest of the text written; a hand edit
  reads with another digest and the same mark, and a write expecting the old digest ends
  `conflict` with the person's text standing; a repeat answers `replayed` and writes nothing;
  ten impossible places are refused with no request reaching the wiki; a value in a variable is
  not read; the guides of this repository, published twice, are created once and then all kept.
- `tests/conformance/test_connector_v1_knowledge.py`: the suite passes with the connector's own
  scenario, and each of the eight faults fails exactly its check.
- `tests/adapters/connectors/test_guides_wiki.py`: S-05 publishes into the wiki and keeps every
  page on the next run; with the connector removed the guides go to the configured directory,
  and with no knowledge system the run escalates at `read-held` and publishes nothing.
- `tests/adapters/connectors/test_knowledge_live.py` was rehearsed against the fake; it runs
  against the wiki once NEED-0021 is provided.

## 3. What was considered

- **The mark inside the page's text, as an HTML comment**, as the directory connector does.
  Rejected: the wiki renders Markdown to HTML and may drop or alter a comment, and a person
  editing the page sees and may break it. Tags are kept beside the page, which is what ADR-0065
  §3 asks.
- **Normalising the text the way the wiki does before hashing.** Rejected: it guesses the
  wiki's rules, and a guess that is wrong makes every page look edited. Reading back what the
  wiki stored needs no guess.
- **Reading the credential from the environment too**, as the chat connector does. Rejected: the
  issue asks for a file only, and a variable shows in a process listing.
- **The live test in a third book on the guides' shelf.** Rejected: the guides' process lists the
  whole shelf, and the test's pages, which the role cannot delete, would grow under it.

## 4. Which entry permits it

M2.4 of `docs/decisions/anchors.taktus.md`: "A change of what the software does, made inside an
agreed scope, that breaks no contract, moves no limit or autonomy level and says nothing public."
The scope is issue #197 in the milestone `0.3.0`, under ADR-0065 and DEC-0176. No contract
breaks: the connector implements `contracts/connector/v1` as it is. No limit moves: S-05's
budget is unchanged, and the connector's demands fit in it. Nothing public is said: the wiki is
private (NEED-0021 §5). The amendment of NEED-0021 is M2.5.

The wiki has no conditional write, so a check against `expected` and the write are two moves.
ADR-0065's bound says a knowledge system with a server checks on its side; this one does not,
and the connector's README states the same window the directory connector has.
