# ADR-0176 — A data-protection request is prepared from what references its subject, and carried out by a person

**Status:** accepted · extends ADR-0006 (the content-free ledger), ADR-0021 (provenance),
ADR-0130 (the case scope names a subject), ADR-0135 (the trace and its retention), ADR-0147
(the register of what acts) and ADR-0165 (the object store) · issue #657, UC-11.2, roadmap
`1.0.0`

## Context

UC-11.2 asks for the data-protection tools — access, rectification, erasure, portability — and
for the evidence of what an installation processes. Four facts shape the answer.

- **The ledger holds no content** (ADR-0006). It cannot be searched for a person. It can say
  what happened to a run, and it must keep verifying whatever is erased.
- **A subject is named in one place only.** A step that serves a case declares a *case scope*:
  the subject, taken from the run's inputs (ADR-0130). The provenance record of that step names
  the subject's identifier (ADR-0130 §7). Nothing else in Taktus knows whose data a run carries.
- **Content lives in four places.** A run's inputs are in the run's document. A step's stored
  result, its artifacts, the messages it received and the records its ledger entries point at
  are bytes in the object store, addressed by digest (ADR-0165). The trace of a worker step is
  in its own store (ADR-0135). The provenance record and the ledger carry identifiers and
  digests only.
- **The object store is shared.** It is one store for the instance, addressed by the digest of
  the bytes. Two runs that hold the same bytes hold one object. Removing it for one run removes
  it for the other.

Three words are used below. A **holding** is one place where Taktus keeps data of a subject: a
run, a step, an object, a trace. A **request** is one data-protection request of a kind for a
subject. **Carrying out** a request is the act that changes or hands over data; only a person
does it.

## Decision

### 1. A request is prepared, then carried out or withdrawn by a person

A request is an aggregate of the governance component (`SubjectRequest`). It names its tenant,
its kind (`access`, `rectification`, `erasure`, `portability`), its subject, its state and the
holdings found when it was prepared. Its states are `prepared`, `carried_out` and `withdrawn`.

*Preparing* finds the holdings (§2) and stores the request. It changes nothing else. Anyone the
surface admits may prepare: a person, or a step of a process that serves such requests.

*Confirming* carries the request out. It names the person who confirms, and that person states
that they checked the requester's identity. A confirmation without the statement is refused. So
is one of a request that is not `prepared`. Before acting, the holdings are found again. Where
they differ from the prepared ones — a new run of the subject, an object gone — the
confirmation is refused, and the request must be prepared again. A person therefore confirms
exactly what they were shown.

*Withdrawing* ends a prepared request without acting.

### 2. A subject is found through what references it

The holdings of a subject are found in two ways, and their union is the answer:

- **the provenance chain**: every record whose scope names the subject (`ProvenanceStore.
  of_subject`, one indexed query);
- **the runs' intake**: every run of the tenant with a step whose scope resolves, from the run's
  inputs, to the subject. This finds a run whose scoped step has not completed yet, and so has
  no record.

For every run found, the holding lists: its inputs by name; every step with its method and
adapter, whether it has a provenance record, and how many trace lines it has; every object the
run references — each step's stored result, artifacts and received messages, and the content
of the run's ledger entries — by digest; how many entries of the run left the system
(`egress.*`, ADR-0022); the steps of other runs that were built on its results
(`ProvenanceStore.derived`); and how many *other* subjects the run's scoped steps serve, as a
number, never their identifiers.

A run is the unit. A run's intake is one case, and everything in the run is about it.

### 3. An erasure removes content, and the record of what happened stays

An erasure of a request's holdings does, for every run that has ended:

1. removes from the object store every object the run references that no other run still
   references (§4);
2. replaces the value of each of the run's inputs with the marker `[erased]`;
3. deletes every trace line of the run's steps (`Traces.erase_run`);
4. records `run.content_erased` on the run's chain, naming the request.

A run still in flight is not erased: its steps still read their inputs. It is listed in the
outcome as pending, and a later request erases it once it ended.

The ledger and the provenance records are not touched. They carry identifiers and digests, and
a digest whose object is gone still says what happened and when (ADR-0006, "Where this promise
ends"). After the erasure the ledger is verified from its first entry, and the provenance chain
of every erased run is verified against its ledger entries
(`domain.service.provenance.verify`). The outcome states both verifications.

Objects are removed before the run's documents change. Removal is idempotent, so a store that
fails half-way leaves a request that can be confirmed again with the same holdings. Each run's
documents, its trace and its ledger entry change in one transaction.

### 4. An object another run still references is kept

The object store is shared (Context). Before removing an object, the erasure reads every run of
every tenant of the instance and collects the digests their step runs reference — results,
artifacts, messages — outside the request's runs. An object among them is kept. The prepared
request already names it, with the reason `referenced by another run`, so the person confirms
knowing it stays. Only a yes or no about a digest crosses from one tenant to another; no
content and no identifier does.

### 5. An export is generated when a person confirms, and never stored

Access and portability are carried out as an *export*: one JSON document, generated at the
confirmation and handed to the caller. It is not stored by Taktus, because a stored copy would be
one more holding of the subject. Its digest is recorded (`subject.exported`), so that the
document a person delivered can be checked against the record later.

The export holds, per run: its inputs, every step's stored result and artifacts with their
content, and the trace lines. JSON content is carried as JSON, other bytes as base64 with their
media type. An **access** export also states the processing: for every step, the adapter and
the location the adapter declares, and for every kind of record, how long it is kept. A
**portability** export carries the data alone.

### 6. A rectification is a list for a person, not a rewrite

Taktus's record of a run that happened is not rewritten: a run that read a wrong value read that
value. A rectification is carried out by a person at the source and, where a result left the
system, through the correction that stays with a person (ADR-0022). The request lists what to
look at: the holdings, the results built on them and the entries that left the system. The
confirmation records that the person carried it out (`subject.rectified`).

### 7. The ledger records the request, never the subject

`LedgerRefs` gains `subject_request_id` (`contracts/shared/v1/LedgerEntry.json`, an optional
property). Every entry of a request names it and, where a person acted, the actor:

| Kind | When | Outcome |
|---|---|---|
| `subject.request_prepared` | a request prepared | its kind |
| `subject.erased` | an erasure carried out | `verified`, or `unverified` where a verification found something |
| `run.content_erased` | a run's content erased, on the run's chain | `erased` |
| `subject.exported` | an access or portability export generated, its digest in `content_digest` | its kind |
| `subject.rectified` | a rectification confirmed | `confirmed` |
| `subject.request_withdrawn` | a request withdrawn | `withdrawn` |

The subject's identifier is in the request's own document, which is kept so that the request
can be answered later: "was this erasure carried out, and when?"

### 8. The evidence is generated from configuration and the ledger

`taktusctl evidence` prints one JSON document for a tenant. Each part has one source:

- **what is processed and by which adapter**: the register of what acts for the tenant
  (ADR-0147), its rows and the steps each adapter serves now, from the active process versions
  and the pools as configured;
- **personal data**: which capabilities the tenant declares personal (ADR-0130 §8), and which
  steps of active versions declare a case scope;
- **where**: each adapter's declared location and the tenant's residency rule (ADR-0116);
- **how long**: the ledger and the provenance records for good, content-free; a run's content
  until it is erased; a trace for the tenant's retention (ADR-0135); backups as the operator
  configured them, outside Taktus (ADR-0087);
- **how much**: each adapter's use over the register's period, and the requests prepared,
  carried out and withdrawn, counted from the ledger's `subject.*` entries.

The document carries `legally_reviewed: false` and the notice the register's inventory carries
(ADR-0147 §2). It is generated by the reporting component (`evidence.processing`), which draws
and stores nothing; the composition gathers the facts.

### 9. Where it lives

- `components/governance`: `SubjectRequest`, the request's rules, and `SubjectRequests`, which
  prepares, confirms and withdraws. Its port `SubjectHoldings` (`governance/ports/subjects.py`)
  finds, erases, verifies and exports.
- `composition/subjects.py`: `RunHoldings`, the port's answer over the runs, the provenance
  store, the ledger, the traces and the object store, and the evidence's facts.
- Ports: `ObjectStore.remove`, `Traces.erase_run`, `ProvenanceStore.of_subject`, with every
  adapter.
- Migration `0097`: the table `subject_request`, and an index over the subject of a provenance
  record's scope.
- Surface: `taktusctl subject` (`prepare`, `list`, `show`, `confirm`, `withdraw`) and
  `taktusctl evidence`.

## Alternatives

- **Searching the content for the identifier.** It would read every object and every run, would
  find the identifier where it means something else, and would still miss data of the subject
  that does not carry the identifier. The case scope is the declaration of whose data a run
  holds (ADR-0130).
- **Erasing per step instead of per run.** A run's intake is one case. A run's later steps read
  its earlier ones; erasing only the scoped step would leave the subject's data in the steps
  built on it.
- **Redacting the provenance record's subject.** The record is written once, and a trigger
  refuses every change (ADR-0021). A record that could be changed for an erasure could be
  changed for anything.
- **The subject in the ledger, as a digest.** A subject identifier has few possible values, so
  a digest is reversed by trying them (ADR-0130, Alternatives). The request's identifier carries
  nothing.
- **Removing every object of the run, shared or not.** It would erase another run's result that
  happens to have the same bytes — a common short value — in this tenant or another.
- **Storing the export.** One more copy of the subject's data, kept for no one.
- **Rewriting a run's inputs for a rectification.** The run would then claim to have read a value
  it never read, and every result it produced would disagree with its own record.
- **Carrying out on confirmation whatever is found then.** A person would confirm one list and
  Taktus act on another.

## Consequences

- `LedgerRefs` gains `subject_request_id`; `LedgerEntry.json` describes the six kinds.
- `ObjectStore` gains `remove`; the object store suite proves it for every adapter, the
  S3-compatible one among them (a `DELETE` of the key).
- `Traces` gains `erase_run`, `ProvenanceStore` gains `of_subject`.
- Migration `0097` adds `subject_request` and the index `provenance_scope_subject`.
- `taktusctl` gains `subject` and `evidence`.

## Where this promise ends

- **A subject is found only where a case scope names it.** Data of a subject in a run without a
  scoped step — an analysis, a run whose author did not declare the case — is not found, as
  ADR-0130 already bounds what is personal.
- **A run is erased whole.** A run whose scoped steps serve several subjects is erased for all
  of them; the prepared request says how many other subjects it serves.
- **Results built on the subject's runs are listed, not erased.** The steps of other runs that
  read them are named in the holdings. Whether they hold the subject's data, and whether to
  include them, is the person's judgement.
- **An object is kept when another run references it**, as its step runs reference it: as a
  result, an artifact or a message. A reference held only by a ledger entry of another run is
  not looked for. Such entries carry records of their own run's calls.
- **The identifier stays.** The provenance records of the subject's cases and the request
  itself keep the subject's identifier. After an erasure it points to nothing.
- **A run in flight is not erased** until it ended and a request is prepared again.
- **Backups are not reached.** A backup taken before the erasure holds the content until the
  backup is gone (ADR-0087).
- **The source systems are not reached.** Taktus erases and exports what it holds itself.
- **The cost is a read of every run of the instance** at preparation and at confirmation. A
  request is a person's act, rare, and its answer must be complete; a faster answer would need
  an index of digests the object store does not keep.
- **The evidence describes the configuration now and the ledger's period.** A process that ran
  last year on an adapter since removed appears in the ledger's counts, not in the register.
- **Not legal advice.** Taktus does not judge a request's lawfulness, an exemption or a
  deadline, and the evidence is not legally reviewed.
