# CLAUDE.md — doctrine for this repository

The durable working doctrine for every session here, human or machine. It outlives individual tasks
and tools. Anything with an expiry date belongs under `docs/`, not here.

**First standing order:** keep this document current. Any change that alters how work is done here
belongs in the same pull request, not after it.

---

## 1. What Taktus is

Taktus is an operating layer for a business. A person states what should be achieved. Taktus breaks
that into processes, decides for each step which method suits it best, runs it or has it run,
measures the result, corrects within an agreed frame, and reports. At autonomy level 4 whole
departments run this way.

The architecture is in `docs/architecture/`, the decisions in `docs/adr/`. **Where code and an ADR
disagree, the ADR wins** — the code becomes the finding, not the ADR a footnote.

---

## 2. Taktus is business-critical

At level 4 a company's day-to-day operation depends on Taktus. That is the intent, not a side
effect. Four requirements follow (ADR-0013):

**A — It runs without interruption.** Several instances, load spread across them, restart without
data loss. A restart resumes at the last step boundary.

**B — A person can take over any process.** Every process Taktus runs carries maintained
instructions. The takeover test passes when a person can run the process without Taktus.

**C — Taktus is repairable without Taktus.** There is a manual way to restore an earlier version
that does not involve Taktus. It is documented and exercised.

**D — For self-development only:** Taktus changes its own repository but does not put itself into
production. A version Taktus built is deployed by another instance or by a person.

---

## 3. AI is the foundation — and AI is not only language models

The single most important mistake this project must not make is treating AI as a synonym for
language models.

Eight method kinds are available per step — `rule`, `statistics`, `ml`, `neural`, `llm`, `worker`,
`human`, `wait`. **Four of them are reproducible.** Reproducibility is therefore not a question of
"AI or no AI" but of which method was chosen.

Every step carries its method, the reason for the choice, the alternatives rejected, and a fallback.
The choice stays under observation; Taktus proposes a change when a cheaper, more reproducible
method would do the same job.

Full detail: `docs/architecture/methods.md`.

---

## 4. Exactness

Every step carries an exactness class that limits which methods may produce its result: `exact`,
`sourced`, `tolerant`, `free`.

**For `exact` there is no exception:** AI methods may propose and prepare, never produce the final
value. A number produced by a language model never reaches the accounting journal. CI enforces it.

---

## 5. The fourteen guiding principles

1. An orchestrator, not another tool landscape. 2. AI at the core. 3. Model- and hardware-agnostic.
4. Tool-agnostic and omnichannel. 5. Coupled or decoupled control, per process. 6. No bus factor of
zero. 7. Transparency fitted to the role. 8. Repeatability and cost control. 9. Efficiency over
verbosity. 10. The whole autonomy range, with guardrails. 11. European values and sovereignty.
12. Production-ready. 13. Freedom instead of vendor lock-in. 14. People at the centre — **never
surveillance or performance assessment of individuals.**

Principle 14 is enforced in the data model: no metric assesses a named person. This includes
decision response times — that analysis belongs to the decider and is visible only to them.

---

## 6. The adapter obligation

Nothing external is called directly. Every outward access goes through one of three adapter types:
**worker**, **connector**, **model**.

`tests/architecture` fails on: a foreign or driver import in the core · **a product name in the
core** · adapter code importing the core · a direct import between two components · a write across a
component boundary.

Processes reference adapters by capability only, never by product name.

**Removal test:** for every integration it must be shown automatically that removing it changes
quality or cost but breaks no process.

---

## 7. Language and stack

Python ≥ 3.13 for everything server-side, including the ML bench. TypeScript for the web app. JSON
Schema for contracts and the shared kernel.

There is deliberately **no second server-side language**. The method choice (section 3) means the
core reasons about models, trains them and evaluates them; a language boundary through that would be
a seam in the wrong place.

---

## 8. Final human control

Two classes of anchor keep an act with a person regardless of the autonomy level:

- **Legal anchors** — legally binding acts.
- **Strategic anchors** — direction: scope, accepting or rejecting a feature, version assignment,
  architectural change, releases, licensing and pricing, anything communicated publicly.

Every organisation defines its own anchors, and the set can be reduced but never emptied. An anchor
halts the run at a step boundary and raises a **decision request**. A free-text answer is never acted
on silently: the interpretation is reflected back and confirmed first.

---

## 9. Working rules

- **One pull request per change.** Conventional Commits.
- **No secret value** ever enters this repository, a file, a log or a message. Configuration
  references secret **names**; the operator creates them. `CREDENTIALS.md` lists name, purpose,
  where it is used and how to rotate it — never values. **The repository is public.**
- **No third-party contributions** while the licence is unsettled (ADR-0012).
- **Generated code is never edited by hand.** Generation lives in `make generate`.
- **Architectural changes arrive as an ADR** before the code does.
- **Documentation freshness is a CI gate.**
- **Everything in English** — code, comments, commits, documentation.
- **Never delete without asking:** no volume, database, backup or process version history. Restores
  count as potentially destructive and follow the same rule.
- **Efficiency over verbosity.** Short descriptions, no restating the obvious, no report without a
  reader.

---

## 10. How to write here

An early draft contained the sentence "Taktus must never sit in the critical path of its own
repair." It had three faults at once: a borrowed term used without explanation, two claims welded
into one sentence, and an assertion that is backwards for Taktus.

Hence the rule for every text in this repository:

- **One idea per sentence.**
- **No technical term before it is explained.**
- **No metaphor where a definition belongs.**

A misunderstood sentence in the documentation becomes wrong code later.

---

## 11. Definition of done

1. violates no guiding principle,
2. passes the architecture tests,
3. passes `make gate-contracts` and the conformance suite if it touches a contract,
4. does not break the removal test,
5. every new step carries method, reason and exactness class,
6. has tests at the right level,
7. carried its documentation along,
8. introduced no secret value,
9. carries an ADR if it has architectural effect.
