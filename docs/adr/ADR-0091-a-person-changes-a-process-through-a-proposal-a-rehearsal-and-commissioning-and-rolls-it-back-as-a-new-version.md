# ADR-0091 — A person changes a process through a proposal, a rehearsal and commissioning, and rolls it back as a new version

**Status:** accepted · makes UC-4.15 buildable (DEC-0186, provisionally Option A), for the
`0.3.0` criterion *a process can be created, viewed, changed and rolled back entirely from the
web app and chat*

## Context
UC-4.15 asks that a person changes a process in their own words, from the web app or the chat.
Taktus answers with a proposal. The proposal is rehearsed, and only the person's commissioning
registers it. Any earlier version can be made current again with one act. Four facts bound the
answer.

- **Registration exists, and makes the version active.** The process component validates a
  bundle and stores it as a version. The version registered last is the active one: the one whose
  triggers fire (ADR-0035, `control-plane.md` §4.2). Registration refuses a version without its
  methods, reasons, classes or checks. It asks for an approval before an autonomy level rises
  (ADR-0026).
- **A rehearsal acts on nothing outside** (ADR-0030). It runs a process version as any run does,
  and answers every outward operation from the recording of the last real call.
- **Understanding a request in a person's words is language.** No rule set states what *also
  check the title before opening the pull request* means for a given bundle. Validating the result
  and computing what changed are rules.
- **The web app writes only what ADR-0063 §4 names**, and the chat answers through its phrasebook
  (ADR-0069). Neither may grow a way to change a process that the other lacks (UC-4.15
  *the same from the web app and the chat*).

## Decision

### 1. A proposal is a record of its own, never a version
The process component gains a **proposal**: the tenant, the process, the version it was made
against, the bundle it proposes, the words of the request, the identity that asked, and its
state — `proposed`, `rehearsed`, `commissioned`, `discarded`. A proposal is not a process version.
No trigger, schedule, overview or level reads a proposal as one. The active version does not
change while a proposal exists.

A proposal is offered only once its bundle passes the validation that registration applies.
Otherwise the request is answered with the findings registration would give, and no proposal is
kept. The difference against the base version is computed by a rule from the two bundles: steps
added, removed and changed, and for each changed step its method, reason, rejected methods,
fallback and class before and after.

### 2. The proposing is a process of Taktus's own
A request is turned into a proposal by a self-operation process, **S-07 Change in dialogue**,
registered like any other:

| Step | Method | Exactness | Why |
|---|---|---|---|
| read | `rule` | `sourced` | the bundle is read as it is registered |
| propose | `llm` | `tolerant` | the request is in a person's words; no rule states what it means for a bundle. Rejected: `rule`, the wording varies too much. Falls back to `human`: the person writes the bundle |
| keep | `rule` | `exact` | the proposed bundle validated as registration would, its difference against the active version computed field by field, and the proposal kept; the model's answer leaves only through it. Its check is a recomputation (ADR-0082) |

The model proposes; the rules decide whether there is a proposal at all. A person may also hand
over the changed bundle directly; it then enters at *keep*, and no model is asked.

### 3. A rehearsal before commissioning
A proposal is rehearsed as ADR-0030 rehearses any run. The rehearsal runs the proposed version
under a reference of its own, `<process>@proposal-<id>`, which no trigger fires and no level
counts as a version. Its inputs are the inputs of the active version's last run, or those the
person gives. The proposal moves to `rehearsed` with the run's identifier. A rehearsal that cannot
run is answered with why — for example an outward operation that has never been called for real
— and the proposal stays `proposed`. A proposal changed after its rehearsal is `proposed` again.

### 4. Commissioning registers, through registration
Commissioning a `rehearsed` proposal hands its bundle to registration, acting for the identity
that commissions. Every check registration applies holds, the approval of a level raise included.
The new version becomes active by registration's own rule. The ledger records
`process.commissioned` with the proposal, the version and the identity. A proposal made against a
version that is no longer the active one is not commissioned; the person is told so and asks again.

### 5. Rolling back registers an earlier version's bundle again
A rollback names an earlier version. Its bundle is registered again as a new version, through the
same registration, with the version it restores named in the record. The ledger records
`process.rolled_back`. Nothing is deleted: every version stays registered and readable by name.
A run under way finishes on the version it started on (ADR-0035).

### 6. One surface, two channels
The HTTP surface gains, under the reader's account key (ADR-0063 §4):

- `POST /processes/{id}/proposals` — a request in words, or a bundle;
- `GET /processes/{id}/proposals/{proposal}` — the proposal, its difference and its rehearsal;
- `POST …/{proposal}/rehearse`, `…/commission`, `…/discard`;
- `POST /processes/{id}/rollback` — the version to restore.

Each answers `404` for a process the reader may not see, as the levels do, and refuses an identity
that may not register versions of it. The web app calls these and nothing else to change a
process. In the owner's conversation (ADR-0069) the phrasebook gains the words of four acts —
`change_words`, `rehearse_words`, `commission_words` and `rollback_words` — and the sentences
Taktus answers them with, given all or none, as ADR-0069 §5 holds for its entries. A change
starts S-07 for the owner; a rehearsal acts on nothing outside and needs no confirmation. A
commissioning or a rollback is read back first, kept as waiting in its thread, and takes effect
only on the same person's confirmation there (ADR-0008); a `no` drops it. Nothing is deleted:
what waits moves to done or dropped.

## Alternatives
- **The proposal as a version that is not yet active.** Registration makes the last registered
  version active, so a proposal stored as a version would need a second notion of *active* in
  every reader of versions. A record of its own keeps registration as it is.
- **The model's proposal registered directly.** The language model would then produce what
  becomes the active version. A variable method never produces what takes effect without a check;
  here the check is the registration's own validation, and the act is the person's.
- **Editing the bundle in a form in the web app.** It is block building by another name, which
  the non-goals rule out as the primary interface. A person may still hand over a bundle; the
  dialogue is the way the use case asks for.

## Consequences
- The process component gains the proposal and two acts, commission and rollback. Registration is
  unchanged.
- `blueprints/self-operation/` gains S-07, with its takeover instructions (UC-6.3).
- ADR-0063 §4 grows by the writes of §6; ADR-0069's phrasebook by three entries.
- UC-1.2's plan is not built by this: a proposal is the plan for one change, and commissioning it
  is the recorded act UC-1.2 asks for. A plan that spans more than one process stays UC-1.2's.

## Where this promise ends
The validation holds a proposal to what registration checks; it cannot tell whether the change is
what the person meant. The difference and the rehearsal let the person see that, and
commissioning is theirs. The rehearsal acts on nothing outside, so it cannot show how an outside
system answers what was never sent to it before; an operation without a recording makes the
rehearsal fail, it does not make it pass. Two proposals against the same version are not merged.
Rights per role (UC-7.3) are not built here: until they are, whoever may register a version may
change and roll back the process.
