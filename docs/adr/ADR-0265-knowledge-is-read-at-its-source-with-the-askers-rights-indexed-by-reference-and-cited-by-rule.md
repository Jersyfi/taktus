# ADR-0265 — Knowledge is read at its source with the asker's rights, indexed by reference, and cited by rule

**Status:** accepted · extends ADR-0014, ADR-0233, ADR-0264 · UC-5.5 §2 · DEC-0228

## Context

UC-5.5 requires one knowledge layer over the organisation's wikis, document stores and
repositories. Every statement drawn from it names its source with a link that opens it. A step
whose result rests on knowledge is `sourced`, and an answer without a source does not leave the
step. Taktus reads with the asker's rights, never with wider ones. It keeps an index of
references and digests, never a second record. A changed or removed source document is
reflected in the index, and an answer never cites a version the source no longer holds without
saying so.

The `knowledge` component published the repository's guides into a wiki through the capability
`knowledge.pages` (ADR-0065). Nothing searched a knowledge source, kept an index or checked a
citation. ADR-0264 made a connector step read with the own credential of the identity a run
acts for.

## Decision

### 1. A knowledge source serves the capability `knowledge.documents`

Two operations, both `read`:

- **`knowledge.documents.search`** takes a `query` and at most `count` documents. It answers
  with the documents the source finds for the credential the call names, each with its
  identifier in the source (`document`), its `title`, the `url` that opens it, the `version`
  the source holds, the `digest` of its text and the text itself (`body`).
- **`knowledge.documents.versions`** takes the identifiers of documents read before. It
  answers, for each, the `version` and `digest` the source holds now, or `absent` where the
  source no longer shows the document.

The capability is separate from `knowledge.pages`, the place the guides are written to. A
source that is searched need not be one that is written, and the directory connector serves
`knowledge.pages` without a search. The wiki connector serves both.

### 2. An answer from knowledge is a process of four steps

The blueprint `knowledge` ships it as K-01:

1. **search** — a connector step on behalf of the asker (ADR-0264). It reads what the source
   shows the asker, and nothing more.
2. **answer** — a language model writes the answer from the documents read, as statements,
   each naming the documents it rests on.
3. **confirm** — a connector step on behalf of the asker reads the versions the source holds
   now.
4. **cite** — the rule `citation` joins the statements to the documents and names each source
   with its link and version.

Every step is `sourced` and declares its check (ADR-0233). The fallback of the two reads is a
person, who answers from the source themselves.

### 3. The rule `citation` lets no answer without a source leave the step

The rule refuses, and the step fails with the reason:

- an answer that is not statements, or that has none;
- a statement that names no source;
- a statement that names a document the search did not read;
- a source without a link.

Its result is the answer as a person reads it, every statement followed by the numbers of its
sources. The list of sources follows, each with title, link and version. Where the version the
source holds now differs from the one read, the source says so: *changed*, with both versions.
Where the source no longer shows the document, it says *removed*. The rule learns what the
source holds now from the confirmation, and from the index where the index observed the
document later than the confirmation did.

The rule's logic belongs to the `knowledge` component. The run reaches it through the port
`Citations` (`components/run/ports/citations.py`). The composition root answers the port from
the component, because components never import each other.

### 4. The index keeps references and digests, never the text

The index is the aggregate `KnowledgeEntry`, one per document of a source in a tenant. It holds
the capability, the document's identifier, its title and link, the version and digest last
observed, when that was, and whether the source held the document then. It keeps the earlier
versions it observed, each with its digest and time. It never holds a document's text.

The index learns from every reading the rule `citation` is given: the documents the search
read and the versions the confirmation read. A newer version replaces the entry's current one
and moves the old one into its history. A document the confirmation found absent is marked
removed. A document read again later is current again.

### 5. Removing a source changes what Taktus knows and breaks no process

A source is a connector by capability (ADR-0003). Without one, K-01's search has no adapter and
falls back to a person: the removal test finds the process *changed*, not *broken*.

## Alternatives

- **One capability `knowledge.pages` with a search added.** The directory connector would serve
  a capability whose search it lacks. The pool chooses a connector by capability, so a process
  could reach one that cannot serve the operation it calls.
- **The index refreshes itself on a schedule with Taktus's own credential.** A document hidden
  from that credential would look removed to everyone, and Taktus would read with rights wider
  than the asker's. Rejected: the index learns only from the asker's readings.
- **The language model cites by itself, and a pattern checks the answer.** A pattern finds a
  link. It does not find whether the link is one the asker read, or whether its version still
  holds.
- **The index keeps the text, so that it can answer without the source.** That is a second
  record (UC-5.5 §3). It would also show a later asker a text the source no longer shows them.

## Consequences

- `connectors/taktus_connectors/bookstack/`: the capability `knowledge.documents` over the
  wiki's search and page reads; its fake answers each token with what that token may view.
- `components/knowledge/domain/model/index.py`: `KnowledgeEntry`;
  `components/knowledge/domain/service/citing.py` and `indexing.py`: the rule and the index's
  observations; `components/knowledge/application/service/cite_answer.py`: both, in one unit of
  work.
- `components/run/domain/model/work.py`: `CitationRule`; `components/run/ports/citations.py`:
  the port; `components/run/application/service/execute_run.py`: its evaluation.
- `composition/knowledge.py`: the port over the component, wired in `taktusctl` and `taktusd`.
- `blueprints/knowledge/`: the blueprint and K-01.
- Tests: `tests/components/knowledge/test_citing.py`, `tests/components/knowledge/test_index.py`,
  `tests/adapters/connectors/test_knowledge_search.py`,
  `tests/composition/test_knowledge_answers.py`.

## Where this promise ends

- A citation says where a statement came from. It does not say the statement is true, and it
  does not prove that the model rendered the document faithfully. The rule checks that each
  statement names documents the asker read. What the statement says of them stays the model's.
- The index is as current as its last reading. A document nobody reads again keeps the version
  and time it was last observed. The rule's *changed* and *removed* cover what the confirmation
  and the index observed, not what the source did after.
- The source's rights are the boundary. A source that shows a person more than it should is the
  source's error, as in ADR-0264. A source that answers a hidden document as absent makes it
  look removed to that person; Taktus cannot tell the two apart.
- The index holds a document's title and link. It is never served as an answer: every answer is
  built from the asker's own reading. A later asker learns nothing from the index that their own
  reading did not show them.
- The run keeps what a step read as its result, as every step does (ADR-0021). The index is the
  only store this decision adds, and it keeps no text.
- Whether connected knowledge improves the quality of work is not measured here. UC-5.5 asks for
  that comparison on the value ledger's figures (UC-9.1), which are not built.
