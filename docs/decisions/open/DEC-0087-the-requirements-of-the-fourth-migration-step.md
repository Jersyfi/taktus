# DEC-0087 — The requirements of the fourth migration step

**Category:** NON-BLOCKING
**Raised in:** [#137](https://github.com/Jersyfi/taktus/pull/137)
**Issue:** [#135](https://github.com/Jersyfi/taktus/issues/135)
**Needed by:** 2026-10-23
**Provisional answer:** Option A. The seventeen use cases of the fourth migration step, and the two blueprint descriptions, are in force with the conditions they add beyond version 2 of the definition and beyond the text in which you stated three requirements yourself; they bind any session that builds one of them before the answer. Marked here and in the status file.

## 1. What this is about

Taktus keeps what it must be able to do as requirements: one file per capability, each saying what
must be achieved, how that is checked, and what is explicitly not required. They were moved in four
steps from the German project definition you wrote. This is the fourth and last step: the knowledge
Taktus draws on, the figures of value and controlling, the views and reports people read, how Taktus
runs and is administered, and two domains described as deployments — finance, and the IT service chat.

It also writes down three requirements you stated in conversation rather than in the definition: **the
channel through which Taktus reaches you** and through which you answer; **the product finding** — what
a project meets that the product lacks becomes an issue in the Taktus repository; and **readable
documentation beyond the repository** — guides for administrators and users in the organisation's own
wiki, generated from the repository.

Seventeen requirements were written. Where one only restates what your definition, your stated text or
the vision already asks, the session wrote it without asking you, as you decided on 2026-10-01. Where the
source gives a sequence and a few words of acceptance, a requirement needs a condition precise enough
that it cannot be met by interpretation, and writing it added substance. That substance is new, and what
a requirement says is yours to decide. This request lists it.

One of the seventeen was never in the definition at all: the bottleneck and waiting analysis (UC-9.5).
It was first stated in the architecture decision on measuring waiting and numbered in conversation. It
is put to you as a requirement now.

## 2. Why you are being asked

Entry M3.15 of `docs/decisions/anchors.taktus.md`: *"What a use case requires — what is new beyond
`docs/vision/` and the owner's project definition; bringing a use case up to them is M2.7: its outcome,
its verification condition and its boundary."* Every condition listed in section 4 is new beyond both,
and beyond the text in which you stated the three requirements. Several are asked at once, so the
question is asked once, as DEC-0030, DEC-0069 and DEC-0082 did.

**Sources checked:** `docs/vision/` — principles 1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13 and 14, the
non-goals and the history give the direction of several conditions (each source is named in section 4)
but not the conditions themselves. The ADRs — ADR-0003, ADR-0004, ADR-0005, ADR-0006, ADR-0008,
ADR-0010, ADR-0013, ADR-0014, ADR-0015, ADR-0021, ADR-0024, ADR-0025, ADR-0026, ADR-0028, ADR-0029 and
ADR-0031 are the source of many conditions, and an architecture decision says how something is built,
not that a use case must require it. Both anchor pages — M3.15 makes what a requirement adds yours, M2.7
covers only restoring, and M2.6 covers where a use case is filed (NTC-0064), not what it requires. The
register — DEC-0030, the same question for the first thirteen use cases, was answered on 2026-10-08 with
Option A, on the reason that each added condition came from an accepted ADR or made a principle checkable
and none moved a limit or an autonomy level. DEC-0069 and DEC-0082, the same question for the second and
third steps, are open with Option A in force. None of the three decides these seventeen, and what a
requirement adds stays yours under M3.15; the precedent is therefore cited in the recommendation below,
not applied in your place. DEC-0041 decides that restoring is the session's, which is how two existing
use cases were brought up to your definition here (NTC-0062, NTC-0063). DEC-0057 (the wiki once Taktus
manages itself) and DEC-0058 (Taktus notices a broken interface and reports it through its channel) are
your answers and are applied, not asked.

## 3. What you must decide

Whether the conditions the seventeen requirements and the two blueprint descriptions of the fourth
migration step add beyond version 2 of the definition, and beyond your stated text, stand.

## 4. What you need to know to decide

**What was added**, per use case. The source of each addition is named: an architecture decision (ADR),
the repository's own text, a principle of the vision, or the session.

| Use case | Serves | Added beyond the definition or your stated text |
|---|---|---|
| UC-6.11 the owner-facing channel (yours) | P4, P7, P10 | the three renderings carry the same identifier, needed items and date, compared by a test; a report missing one of its four parts — what, the steps, what stands still, by when — is not sent (from ADR-0028); only your identity, or someone you named, can answer, and an answer from anyone else is not filed; a task in a ticket system closed without an answer files nothing; a message that cannot be delivered stays visible in the repository and the web app with the failure shown; the language of the message is configuration, German for this project (session) |
| UC-6.12 the product finding (yours) | P11, P12, P14 | an instance raises a finding on its own only for a block whose recorded cause is a lack of the product, decided by a rule, never by a model (session, as the emergency stop); the same lack met again adds to the open finding instead of opening another; a finding carries no content of the project, no personal datum and no secret, because the Taktus repository is public (ADR-0006); an instance of another organisation sends findings to the Taktus repository only where its operator enabled it (principle 11) |
| UC-13.6 documentation beyond the repository (yours) | P1, P6, P14 | every page names the files and the commit it was generated from; a change reaches the guides at the next run, at least daily, and a page whose sources changed shows that it is out of date; a page edited by hand in the wiki is reported, not overwritten silently, and the repository stays the source (session); the guides follow the repository's writing rules (`CLAUDE.md` §10) and carry no secret or internal address; where no wiki is configured the guides are plain files |
| UC-5.3 tickets in the tool of choice | P1, P4 | a ticket the tool refuses is a failed step with the reason, never half-filled; links in the tool where it can, named in the text where it cannot (session); a repeated step creates no second ticket (ADR-0024); Taktus keeps the ticket's identifier and a link, never a copy (principle 1) |
| UC-5.5 knowledge | P2, P4, P7 | an answer from knowledge is of the exactness class *sourced* or stricter and does not leave its step without a source (ADR-0014); Taktus reads with the asker's rights, never wider ones, tested with two identities; an answer never cites a version the source no longer holds without saying so; the gain from connected knowledge is measured by comparing the same work with and without it (session) |
| UC-5.6 the data warehouse | P1, P7, P12 | a figure feeding an *exact* step comes from a query fixed and reviewed in the process version; a query a model writes during a run feeds only a *tolerant* or *free* step (ADR-0014); the warehouse is queried with the identity Taktus acts for, tested with two identities (session); the reading that triggered a threshold is in the step's provenance (ADR-0021) |
| UC-6.5 Taktus explains what it does | P2, P7 | an explanation states only what the records hold, and a model-phrased explanation with a figure the records do not hold fails a test (session); the same question from two roles gets the same facts at different depth; nothing is left out of a short explanation that would change its meaning |
| UC-6.6 the proof of value | P7, P8, P14 | an assumption, such as the time a case took by hand, is shown with who set it; an error avoided counts only where a check found it or a wrong result was caught before it left (ADR-0021, session); personnel cost rates are per role only (principle 14) |
| UC-6.7 the bus-factor index | P6, P13, P14 | a process with no test result, or a result for an earlier version or configuration, counts as not passed; a removal test never run shows as unknown, never as passed; a role counts where a process's takeover instructions require it; a deterioration's proposal names the failing test and the step that would restore it (session) |
| UC-9.1 the controlling cockpit | P7, P8 | a simulation of a higher autonomy level is computed from the decisions people took at the current level, names its assumptions, is marked as a simulation and changes nothing (session, ADR-0026); cost only in Takt and money (ADR-0010) |
| UC-9.2 the transformation | P7, P10 | a department's maturity is computed from its processes' autonomy, methods and tests, never entered by hand; every backlog entry names its source and its expected benefit, marked as an expectation (session) |
| UC-9.3 the value balance | P8, P10, P14 | a personnel cost rate per person cannot be configured, and a test fails a person attribution in the data model (principle 14, as UC-13.5); a process without takeover instructions shows that its revert analysis cannot be made; a recommendation to optimise names first whether a more reproducible method would do (ADR-0004, ADR-0015); a recommendation to raise autonomy is a proposal to the owner (ADR-0026) |
| UC-9.4 discovering processes | P6, P10, P14 | the five stages are ledger entries in order; a discovered process starts at level 1 or 2 with takeover instructions from its first version; a pattern found in a person's own tools is shown to that person first and goes further only with their agreement, as a procedure, never as how the person works (principle 14); one process through the interview for a beginner and for an expert reaches the same result (session) |
| UC-9.5 bottleneck and waiting analysis | P8, P14 | **the whole use case**, in no version of the definition: the seven causes of a block, the marginal value of a higher limit — exact for tokens, quota and compute, an estimate for money — a method change checked before a limit raise, a decider's response times visible to that decider alone with a test in the data model, the four ways to wait less on people (ADR-0015) |
| UC-13.4 joy in daily use | P9, P14 | the personal dashboard is private by default (as UC-13.5); no points, badges, levels, streaks, rankings or comparisons; a first automation in under 30 minutes, measured in the trial of UC-10.3 (session's reading of "minutes, not hours"); successes shown where the person is, at their interval, or never (principle 9) |
| UC-10.1 runs anywhere, on any hardware | P3, P11, P12 | both the one-command install and the infrastructure-as-code deployment exercised by an automated test; one release in every variant, tested with the same process in two; no licence server, account or telemetry sent to the maker (session, principles 11 and 13); no instance runs on infrastructure it administers (ADR-0025) |
| UC-10.2 administration | P7, P12 | every administrative act in both the command line and the web app, tested; an act asked in dialogue is a plan a person with the right commissions and needs no wider right (session); a maturity cannot be set by hand; a restore asks a person first (`CLAUDE.md` §9); an update is applied only when a person commissions it, and the previous version can be restored without Taktus (ADR-0013) |
| Finance (UC-15.2), a description | — | an amount or account reaches the accounting journal only from a reproducible method or a person's confirmation, and recurring bookings run as rules (ADR-0014, `CLAUDE.md` §4) |
| IT service chat (UC-12.2), a description | — | escalation hands over the conversation as the situation package (UC-4.5); a request becomes at most one ticket (ADR-0024) |

**Where your text is superseded, nothing was asked.** Your text is marked as superseded, never deleted,
in three use cases, each pointing at the decision that moved past it. *The owner-facing channel*: you said
the three renderings come from the ledger; the ledger holds no text (ADR-0006), so the event is a ledger
entry and the renderings are composed from the record it references. *The value balance*: the cost of
artificial intelligence is accounted in Takt and money for all work, not as tokens alone (ADR-0010), and
a more reproducible method is the first way to optimise, a cheaper model the second (ADR-0004).
*Administration*: no instance changes the infrastructure it runs on (ADR-0025), and for the Taktus
project a version Taktus built is deployed by another instance or a person (ADR-0013). Those are your
earlier decisions applied, not new ones.

**Where things were filed, nothing was asked either** (NTC-0064): runs anywhere in `governance`,
administration in `identity`, the bottleneck analysis in `accounting`, by the rule that a requirement
lives with the component whose data it concerns. The connector interface (definition UC-5.4) stays carried
by architecture, as the migration planned, because its conformance suite already verifies it.

**Versions the roadmap does not name**, proposed by the session: UC-5.5, UC-6.5 in `0.3.0`, with the web
app and sessions with project knowledge; UC-5.3, UC-13.4 in `0.5.0`; UC-9.4 in `0.6.0`, with the coach;
UC-5.6, UC-9.2 and the IT service chat in `0.7.0`, with the second domain; UC-10.2 in `0.3.0`; UC-10.1 in
`1.0.0`. The finance domain stays off the roadmap. Every other version is the roadmap's: the channel and
the finding in `0.2.0`, documentation beyond the repository in `0.3.0`, value, the bus-factor index and
the bottleneck analysis in `0.5.0`.

All seventeen are *specified*: nothing of them is built. Changing a requirement later is possible, but
never in the change that implements it.

## 5. Options

### Option A — the added conditions stand (recommended)

- **Meaning:** the seventeen requirements and the two descriptions, with what they add, are the standard
  the next changes are held to, including the proposed versions.
- **Consequence:** the owner-facing channel and the product finding of `0.2.0` are built against UC-6.11
  and UC-6.12 as written.
- **Effort:** none now.
- **Reversibility:** cheap until a use case is built; after that, a change is a request per use case,
  which is the intended cost.
- **Why recommended:** each added condition either comes from an architecture decision you already
  accepted, from the repository's own rules, or makes a principle checkable that was only asserted —
  principle 14 above all, in nine of them; none moves a limit or an autonomy level, and where two
  readings were possible the stricter was taken. It is the reason you accepted for the first thirteen
  (DEC-0030).

### Option B — they stand, except the ones you name

- **Meaning:** you name use cases and the condition you want changed, removed or read otherwise in each —
  for example who besides you may answer in your channel, or whether a foreign instance may send findings
  without its operator enabling it; a session changes them in a change of its own.
- **Consequence:** those use cases wait until the change is merged; the others are in force.
- **Effort:** an hour of your reading, a session's afternoon.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing: the provisional answer is in force. If no answer arrives by 2026-10-23, the owner-facing channel
(#85) and the product finding (#86) of `0.2.0` are built on Option A, and changing an added condition
afterwards costs a request per use case instead of one edit now.

## 7. How to answer

"DEC-0087: Option A." — or "DEC-0087: Option B" followed by each use case and the change you want in it —
in issue [#135](https://github.com/Jersyfi/taktus/issues/135). A free-text answer is read
back as an interpretation and confirmed before it is acted on.
