# Blueprint: knowledge

Answers from the organisation's own knowledge — use case UC-5.5. A person asks; Taktus searches
the organisation's knowledge sources with that person's own rights, answers from what they show
them, and names the document every statement came from, with a link that opens it (ADR-0265).

Taktus replaces no wiki and no document store (principle 1). The sources stay the record. What
Taktus keeps of them is an index of references and digests, never their text: which document was
read, where it is, which version and when. A cited statement is as good as its source; the
answer says where it came from, not that it is true (UC-5.5 §3).

## Processes

| Process | What it does | State |
|---|---|---|
| [K-01 Answer from knowledge](processes/K-01-answer-from-knowledge.yaml) | a question answered from the documents a search through `knowledge.documents` finds, on behalf of the asker; every statement names the documents it rests on, checked by the rule `citation`; a source changed or removed since the reading says so | Built (`tests/composition/test_knowledge_answers.py`) |

## What it needs

- **A connector serving `knowledge.documents`.** The wiki connector serves it
  (`connectors/taktus_connectors/bookstack/`). Another source — a document store, a repository's
  documentation — is another connector serving the same capability.
- **Each asker's own credential for the source**, mapped by the operator in
  `TAKTUS_PERSONAL_CREDENTIALS` to the parameter `KNOWLEDGE_TOKEN` (ADR-0264). A person without
  one gets nothing from the source: the search fails before any call, and a person answers.
- **Models of the purposes `triage` and `support`.**

## What it does not do yet

- **More than one source in one answer.** K-01 searches the one connector that serves
  `knowledge.documents`. Joining several sources in one answer is a step per source.
- **Measuring what knowledge adds.** UC-5.5 asks that the same work with and without a source is
  compared on the value ledger's figures (UC-9.1). Those figures are not built, so nothing is
  compared yet.
