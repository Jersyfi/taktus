# DEC-0082 — The requirements of the third migration step

**Category:** NON-BLOCKING
**Raised in:** [#132](https://github.com/Jersyfi/taktus/pull/132)
**Issue:** [#131](https://github.com/Jersyfi/taktus/issues/131)
**Needed by:** 2026-10-23
**Provisional answer:** Option A. The twenty-seven use cases of the third migration step are in force with the conditions they add beyond version 2 of the definition, and bind any session that builds one of them before the answer. Marked here and in the status file; the migration's working file, which marked it too, was deleted at the migration's end (`docs/usecases/NUMBERING.md`).

## 1. What this is about

Taktus keeps what it must be able to do as requirements: one file per capability, each saying what
must be achieved, how that is checked, and what is explicitly not required. They are being moved in
four steps from the German project definition you wrote. This is the third step: how a person
commands and plans with Taktus, who a sender is, the catalogue of models, agents, connectors, skills
and blueprints, the interface every execution unit is attached through, the skill lifecycle, and the
limits that hold resources.

Twenty-seven requirements were written. Where one only restates what your definition or the vision
already asks, the session wrote it without asking you, as you decided on 2026-10-01. Where the
definition gives a sequence and a few words of acceptance, a requirement needs a condition precise
enough that it cannot be met by interpretation, and writing it added substance. That substance is
new, and what a requirement says is yours to decide. This request lists it.

One of the twenty-seven was never in the definition at all: the session with project knowledge
(UC-1.8). It was first described in the repository's blueprint for product development and numbered
in conversation. It is put to you as a requirement now.

## 2. Why you are being asked

Entry M3.15 of `docs/decisions/anchors.taktus.md`: *"What a use case requires — what is new beyond
`docs/vision/` and the owner's project definition; bringing a use case up to them is M2.7: its
outcome, its verification condition and its boundary."* Every condition listed in section 4 is new
beyond both. Several are asked at once, so the question is asked once, as DEC-0030 and DEC-0069 did.

**Sources checked:** `docs/vision/` — principles 1, 2, 3, 6, 7, 8, 10, 11, 12, 13 and 14, the
non-goals and the history give the direction of several conditions (each source is named in section
4) but not the conditions themselves; the history names the skill format as undecided and the
distinction between command and rollout channels as not yet written down. The ADRs — ADR-0003,
ADR-0004, ADR-0005, ADR-0007, ADR-0011, ADR-0014, ADR-0021, ADR-0022, ADR-0024, ADR-0026, ADR-0029,
ADR-0030, ADR-0031 and ADR-0033 are the source of many conditions, and an architecture decision says
how something is built, not that a use case must require it. Both anchor pages — M3.15 makes what a
requirement adds yours, M2.7 covers only restoring. The register — DEC-0030, the same question for
the first thirteen use cases, was answered on 2026-10-08 with Option A, on the reason that each added
condition came from an accepted ADR or made a principle checkable and none moved a limit or an
autonomy level. DEC-0069, the same question for the seventeen of the second step, is open with
Option A in force. Neither decides these twenty-seven, and what a requirement adds stays yours under
M3.15; the precedent is therefore cited in the recommendation below, not applied in your place.
DEC-0041 decides that restoring is the session's, which is how two existing use cases were brought up
to your definition here (NTC-0050, NTC-0051). DEC-0028, answered, is applied in UC-14.2 and asks
nothing new.

## 3. What you must decide

Whether the conditions the twenty-seven requirements of the third migration step add beyond version 2
of the definition stand.

## 4. What you need to know to decide

**What was added beyond version 2**, per use case. The source of each addition is named: an
architecture decision (ADR), the repository's own text, a principle of the vision, or the session.

| Use case | Serves | Added beyond version 2 |
|---|---|---|
| UC-1.2 planning together in dialogue | P2, P10 | a plan lacking one of its four parts cannot be commissioned; every estimate names its basis; approving a step is not commissioning; a plan changed after commissioning is commissioned again (session); a plan ends in a one-off run or a process version (`control-plane.md` §3); a plan with a step that cannot be estimated is refused (ADR-0005) |
| UC-1.3 configuring tools after the plan | P1, P2, P12 | what undoing a change needs is recorded before it is made, and a change whose undoing cannot be stated is handed to a person (session); an action that cannot safely be repeated is never repeated (ADR-0024); the target is reached with the commissioning identity's credential |
| UC-1.5 asking for status and steering | P7, P10 | the answer shows only what the asker may see and is drawn from the ledger (principle 7); a request is acknowledged at once and confirmed when it took effect; only an identity with the right steers a run (session) |
| UC-1.8 a session with project knowledge | P2, P6 | **the whole use case**, in no version of the definition: persistent and bound to a project, one session on two surfaces, sources named, only what the participant may see, acts on nothing directly, what it settles recorded outside the session (blueprint UC-01, principle 6) |
| UC-1.4 the organisation's structure | P1, P6, P7 | every object belongs to exactly one unit; a test moves a process and finds visibility, sharing and cost following; where a knowledge system is configured it is the record, and Taktus keeps a link, not a copy (principle 1) — see below |
| UC-1.6 projects and spaces | P1, P7, P14 | a project refers to what it groups and copies nothing; tasks and documents stay in the organisation's own systems (principle 1) — see below; nothing of a private project appears in any view, report, session, search or figure of a shared one; only its owner moves something out of it |
| UC-1.7 every command belongs to one identity | P4, P12 | a link is never inferred from a matching name or address; after a revocation the next event is from an unknown sender (session); the identity is set by the identity component, never by the connector (`control-plane.md` §2) |
| UC-10.3 usable by people who are not technical | P10, P14 | a trial with at least three people, every stop fixed or recorded; the guided start begins at autonomy level 1 or 2; no technical term unexplained (session) |
| UC-13.1 a guided and an expert mode | P7, P14 | a test pursues one intent both ways and compares; a setting not asked about is shown with its value and why; the mode is a preference, not a permission (session) |
| UC-13.3 the automation coach | P9, P14 | hints shown to the person only (principle 14, as UC-4.4 already does); the person sets how many a week; a dismissed hint is not repeated; switching off stops the observation; whether automations last is shown to the person, aggregated for anyone else |
| UC-5.8 observability and evaluation platforms | P1, P11, P13 | a platform's evaluation adds to Taktus's own and never replaces it (from the removal test); masking proven by a test |
| UC-8.1 any model connected | P3, P13 | one process run against a local and a remote model by configuration alone; every answer's provenance names its model (ADR-0021) |
| UC-8.2 routing to a model by task | P3, P8, P11 | the route and its reason in the provenance; routing reproducible from the ledger; only models that passed the step's evaluation are eligible; never outside residency or exactness (ADR-0014); routing never changes the method (ADR-0004) |
| UC-8.3 running on own hardware | P3, P11 | a test with the route to outside providers closed; local models bound by default in the configuration for individuals and small organisations |
| UC-8.4 repeatable despite flexibility | P8 | every variable step declares a tolerance, bounded by its exactness class; room for creativity only where the class is `free` (ADR-0014); a drift beyond tolerance is a deviation finding |
| UC-8.6 the model hub | P3, P13 | an entry missing a part cannot be shared; a trained model enters with version, owner and evaluation history (ADR-0004); a person's use visible to that person only; withdrawing a model is a removal whose verdict is known first |
| UC-8.7 the agent hub | P2, P7, P12 | diagram and description generated from the version, never edited apart; a test with two callers of one shared agent; no caller above the agent's stated level |
| UC-8.8 sharing connectors per circle | P4, P12 | a test with two identities whose source permissions differ; the level-3 maturity threshold applies; a person's use visible to that person only |
| UC-8.11 one agent, many roles | P8, P12 | a person with several roles who does not choose gets the profile with the fewest rights; a test shows a core change held back by one profile's failed evaluation |
| UC-12.1 rolling out assistants | P1, P4, P12 | a message in a rollout channel never becomes a command to Taktus; every channel is configured as one kind or the other, with a test; an assistant can be switched off and exported (the distinction itself is the definition's chapter 5) |
| UC-12.3 composing any case | P1, P2 | a test takes one of the definition's examples to a registered process without code |
| UC-13.2 method scaffolds | P6, P13, P14 | Taktus checks a project against its scaffold and names what is missing; a scaffold writes into the organisation's own systems (principle 1) |
| UC-14.1 the worker interface | P3, P12, P13 | two proof cases, a script and a training run (ADR-0007); a second real worker of each shape before features build on worker behaviour (`contracts.md` §4); "hours, not weeks" read as one working day for a person new to the repository, in a recorded trial (session) |
| UC-14.2 the skill lifecycle | P2, P8, P14 | the stages in order, each a ledger entry; the dry run is a rehearsal (ADR-0030); a skill never loosens a step's exactness (ADR-0014); a shared skill names no person; the fallback is decided by a rule, never by a language model (session, as ADR-0023 decides the emergency stop) |
| UC-14.3 the skill hub | P13, P14 | not even an administrator can share a person's own skill; a person's use visible to that person only |
| UC-15.1 domain blueprints | P1, P10, P13 | a blueprint missing a part does not enter the catalogue; "conservative" read as level 1 or 2; no process of an instance runs before its owner is named (UC-15.5); a later blueprint version is offered to an instance, never applied |
| UC-8.10 strict limits that do no harm | P8, P10, P12 | a child's limit never admits what its parent refuses (as UC-8.5); whether a limit does harm is decided by a rule over the ledger, never by a language model; a person's held work visible to that person, aggregated for anyone else (as UC-8.5) |

**Two places where your definition and the vision pull apart.** The stricter reading was taken in
each.

- *Projects (UC-1.6).* The definition gathers a project's conversations and tasks in one space.
  Principle 1 forbids Taktus a task list or a document store where the organisation has a ticket or
  knowledge system. A project therefore refers to the organisation's tickets and documents and does
  not hold its own. If you want a project to hold tasks of its own, say so under Option B.
- *Where things are documented (UC-1.4).* The definition says inside Taktus and/or in the
  organisation's knowledge system. Under principle 1, where a knowledge system is configured it is
  the record, and Taktus keeps a link to it, not a second copy.

**Versions the roadmap does not name**, proposed by the session: UC-1.3 in `0.4.0`, with the second
tenant's onboarding; UC-1.5 and UC-1.4 in `0.3.0`, with the web app; UC-1.6, UC-5.8, UC-10.3, UC-13.1
and UC-13.3 in `0.6.0`, with the catalogue and the skill lifecycle; UC-12.1, UC-12.3 and UC-15.1 in
`0.7.0`, with the second domain; UC-14.1 and UC-8.10 in `0.5.0`, where a worker can first reach
*verified* and where limit recommendations must come with numbers. Every other version is the
roadmap's.

**Where your definition is superseded, nothing was asked.** Your text is marked as superseded, never
deleted, in seven use cases, each pointing at the decision that moved past it: undoing a
configuration in a target system stays with a person (UC-1.3); a pause lands on the next step
boundary rather than immediately (UC-1.5); an observability platform is reached through the
telemetry port and a connector, and can never be the leading version of a prompt (UC-5.8); the model
contract is Taktus's own, and the common chat dialect is only how one adapter speaks (UC-8.1); a limit
yields by at most one step's recorded overrun, and every step is estimated, not only a worker's
(UC-8.10); n has the floor you gave it (UC-14.2); a blueprint leaves Taktus as plain files, and the
open bundle specification is after `1.0.0` (UC-15.1). Those are your earlier decisions applied, not
new ones.

**What is missing before two of them are built.** The skill lifecycle (UC-14.2) and the skill hub
(UC-14.3) need an architecture decision on the skill format first. It is named as missing, not
written.

Seven of the twenty-seven are partly built and name the tests that prove the part: UC-1.2
(commissioning is recorded), UC-1.7 (nothing executes without an identity), UC-5.8 (traces nested,
nothing exported without an endpoint), UC-8.1 (the model contract's checks), UC-8.4 (an answer that
fails its check does not leave the step), UC-8.10 (admission and the stop at a boundary), UC-14.1 (the
conformance suite, two workers, maturity derived from both halves). Changing a requirement later is
possible, but never in the change that implements it.

## 5. Options

### Option A — the added conditions stand (recommended)

- **Meaning:** the twenty-seven requirements, with what they add beyond version 2, are the standard the
  next changes are held to, including the two stricter readings and the proposed versions.
- **Consequence:** the fourth step of the migration builds on them, and the `0.2.0` work on the
  identity component is held to UC-1.7.
- **Effort:** none now.
- **Reversibility:** cheap until a use case is built; after that, a change is a request per use
  case, which is the intended cost.
- **Why recommended:** each added condition either comes from an architecture decision you already
  accepted, from the repository's own text that the decisions rest on, or makes a principle checkable
  that was only asserted; none moves a limit or an autonomy level, and where two readings were
  possible the stricter was taken. It is the reason you accepted for the first thirteen (DEC-0030).

### Option B — they stand, except the ones you name

- **Meaning:** you name use cases and the condition you want changed, removed or read otherwise in
  each — for example tasks held in a project, or a version; a session changes them in a change of
  their own.
- **Consequence:** those use cases wait until the change is merged; the others are in force.
- **Effort:** an hour of your reading, a session's afternoon.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing: the provisional answer is in force. If no answer arrives by 2026-10-23, the identity
component of `0.2.0` is built against UC-1.7 on Option A, and changing an added condition afterwards
costs a request per use case instead of one edit now.

## 7. How to answer

"DEC-0082: Option A." — or "DEC-0082: Option B" followed by each use case and the change you want in
it — in issue [#131](https://github.com/Jersyfi/taktus/issues/131). A free-text answer is read back as an interpretation and confirmed before it
is acted on.
