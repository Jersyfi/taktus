# Migrating the project definition

The project definition lived outside the repository. This file says where each part goes, what
is superseded, and what has to be decided during the move.

**The source is version 2 of the definition** — epics E1 to E15, eleven chapters, market chapter
dated September 2026. The owner holds it. An earlier version of 2026-09-01 (E1 to E13, seven
chapters) was used by mistake when step 1 was first written; what that changed is under *Version
2 against the version of 2026-09-01* below.

**It is a working document.** When the migration is complete it is deleted, and nothing here
survives except in the files it points to.

**Where it stands (2026-09-29):** step 1 is done — `docs/vision/`, the use case format, the gates
`make gate-vision` and `make gate-usecases`, the two rules in `CLAUDE.md` and in the anchor files,
findings 1 to 3 decided, and thirteen use cases seeded so that every principle is served (their
requirements, and where they differ from version 2, are DEC-0030). Steps 2 to 4 are open.
`docs/status.md` §1 says the same.

---

## The rule for the whole migration

**Do not transcribe.** The definition predates most of the architecture decisions. Where it
contradicts an accepted ADR, name the contradiction and mark what is superseded as superseded.
**Never quietly adjust it to match the code** — that would destroy exactly the check the vision
layer exists to provide.

Expect to find that parts of the definition are now wrong. That is the purpose of the exercise,
not an accident of it.

---

## Chapters

| Chapter | Verdict |
|---|---|
| 1 Vision and positioning | → `vision/vision.md`. **Rewritten**: method selection is now the central differentiator and was absent |
| 2 Market analysis | → `vision/market.md`. **Marked stale.** Uncited figures, product examples left out, not maintained; its differences from the chapter are stated in its warning |
| 3 Naming | → `vision/history.md`. Settled |
| 4 Guiding principles | → `vision/principles.md`. **Each now carries its reasoning and what it forbids.** 2, 8 and 13 substantially reworked |
| 5 Architecture guardrails | Dissolved into the ADRs, except two parts: the open skill format (`SKILL.md`), which needs an ADR before E14's skill lifecycle is built, and the distinction between command channels (E1, the sender's rights) and rollout channels (E12, the agent's rights plus the user's credentials). Reasoning kept in `vision/history.md` |
| 6 Actors | → `vision/personas.md` |
| 7 Use cases | → `usecases/`, by component. See below |
| 8 Non-goals | → `vision/non-goals.md`. **One corrected**: model training |
| 9 Development path | Superseded by `docs/roadmap.md`. Its guiding thought, "Taktus builds Taktus — every friction is a product finding", becomes a requirement below (*the finding*) |
| 10 Beyond v1 | → `vision/beyond-1.0.md` |
| 11 Open questions | → `vision/history.md`; the two still open are DEC-0028 (question 7) and DEC-0029 (question 9) |

---

## The use cases, by epic

Components as under `src/taktus/components/`. Where an epic describes a *deployment* rather than
a capability of the core, it belongs in `blueprints/`, not here.

| Epic | Goes to | Notes |
|---|---|---|
| **E1** Command, co-planning, interaction | `command/`, and UC-1.4, UC-1.6 and **UC-1.7 channel identity** to `identity/` | UC-1.7 is new in version 2: every command belongs to exactly one authenticated identity; unknown senders get a question, never an execution. Largely decided in `docs/architecture/control-plane.md`; the identity component is `0.2.0`. UC-1.8 (session with project knowledge) is in no version of the definition and must be included |
| **E2** Engineering orchestration | **`blueprints/dev-orchestration/`** | Not core use cases. They describe one deployment of the core, and two of them already run |
| **E3** Repository hygiene | **`blueprints/dev-orchestration/`** | Same |
| **E4** Process engine | `process/` and `run/` | The largest group, and the one with the numbering problem below |
| **E5** Integration and knowledge | `knowledge/`; UC-5.1, 5.2, 5.4 are architecture and already decided (UC-5.2 is seeded in `process/`) | UC-5.8, new in version 2, connects an observability or evaluation platform — trace export, eval backend, prompt synchronisation, cost reconciliation — and is optional: removing it must pass the removal test. Filed in `catalog/` as an integration with a maturity level |
| **E6** Reporting and transparency | a new component, **`reporting`** (ADR-0029); UC-6.1 to `ledger/`, UC-6.3 to `process/`, UC-6.7 to `value/` | UC-6.3 is the takeover test. UC-6.7, the bus-factor index, is new in version 2: computed from real takeover and removal test results, never estimated, per role and process, never per person. Finding 2, decided |
| **E7** Governance and autonomy | `governance/` | UC-7.4 (decision request) was added later and is largely built |
| **E8** Model platform | `catalog/` and `accounting/` | UC-8.5 must be reconciled with ADR-0005 and ADR-0010, which have moved well beyond it. UC-8.10 in version 2 already says admission control and step boundaries as ADR-0005 does. UC-8.11 role-based agents is new in version 2: one agent, a shared core and role profiles that only narrow rights, every profile's evals green before a core change goes live — `catalog/`, as governance.md §5 already describes it |
| **E9** Controlling | `value/` | UC-9.5 (bottleneck and waiting analysis) was added later |
| **E10** Platform and administration | Mostly architecture, already decided. **UC-10.3 (usability for non-technical people)** goes to `command/` (ADR-0029) | |
| **E11** Security, privacy, European values | `governance/` | Needs a check against what exists: much is claimed, little is built |
| **E12** Assistant factory | `catalog/` and `blueprints/` | Depends on E8; not before the catalogue exists |
| **E13** Enablement | no component of its own (ADR-0029): `command/`, `catalog/`, `reporting/`, each with `epic: E13` | Finding 3, decided |
| **E14** Execution layer: workers, skills and the learning loop | `catalog/`, step 3 | **UC-14.1 the worker interface**: every executing unit is attached through one interface — take an assignment with its frame and autonomy, stream events, report tokens and cost per step, estimate before start and signal step boundaries, hand over artifacts, get credentials injected and never store them, receive only the tools the process allows; each adapter passes a conformance suite and gets its maturity from it; processes name workers by capability; replacing one passes the removal test; a reference worker ships. **Largely decided and built**: ADR-0007, `contracts/worker/v1`, the conformance suite, two workers — the first candidate for `verified`. **UC-14.2 the skill lifecycle**: observation → draft skill in an open format → eval and dry run → approval by autonomy level (a person at levels 1 to 3; automatic after n passed evals at level 4) → versioned in production → takeover documentation updated → quality measured, automatic fallback to the previous version. No skill reaches production without passed evals; every skill's origin is traceable; learning at process level, never a person's behavioural pattern; a skill from personal use belongs to the person. The floor for n is DEC-0028; the skill format needs an ADR. **UC-14.3 the skill hub**: approved skills in the catalogue per sharing circle, exportable singly and bundled, a personal skill shared only by the person's decision. Nothing of 14.2 and 14.3 is built; the roadmap places them in `0.6.0` |
| **E15** Virtual agent business: domains as blueprints | split — the capabilities into the core, the domains into `blueprints/` | The level-4 vision itself: an organisation whose departments run as orchestrated process chains, with people as owners and deciders. **UC-15.1 domain blueprints** — instantiating a department from the catalogue by co-planning, starting at conservative autonomy; a blueprint is a template, exportable, capability-named, integrated in reporting, controlling and governance — is a capability of `catalog/`, step 3. Its table of ten example domains, and what stays with a person in each, goes to `blueprints/README.md`, step 4. **UC-15.2 the finance reference domain** — capture, match and pre-account documents, prepare filings and hand them to tax advisers; legal acts always at human-in-the-loop, configurable per jurisdiction, immutability in the accounting system, not in Taktus — is a deployment: `blueprints/finance/`, step 4. It is not on the roadmap yet; the roadmap's second domain is systems operation. **UC-15.3 partner interfaces** — open exchange formats first, a documented data contract for every interface, deviations escalated, never silently corrected — goes to `process/`, step 2: a data contract is part of a process version, and its checks are UC-4.10's source-shape checks. **UC-15.4 end-to-end chains across domains** — order-to-cash, procure-to-pay; context and documents handed over completely at every boundary, a chain with its own value balance and service levels, a legal anchor in one link stopping the chain at a step boundary — goes to `process/`, step 2. **UC-15.5 the responsibility anchor** — every instantiated domain has exactly one human owner who sees it, receives its escalations, decides its autonomy raises and is the addressee of its takeover test; the legal-anchor catalogue per domain and jurisdiction, configurable and never empty — goes to **`governance/`**, step 2. The catalogue's review is DEC-0029 |

---

## Four things that must be resolved during the move

**1. The numbering is broken.** *Decided: `NUMBERING.md`.* The same identifier has been used twice in different
conversations, notably around `UC-4.7` and `UC-4.8`, and exactness ended up as `UC-4.13` in the
repository while an earlier proposal called it `UC-4.8`.

**The repository wins.** Reconcile every identifier against what is already in
`docs/usecases/`, keep those, renumber only what has never been written down, and record the
mapping so that older references remain findable.

**2. Reporting has no component.** *Decided: ADR-0029 — `reporting` is a component that owns views
and no figure.* E6 is the views, the reports and the audit record. It splits
awkwardly across `ledger` and `value`, and neither is right for a role-based view.

Either a `reporting` component is missing from the architecture, or views are deliberately
cross-cutting and belong somewhere else entirely. **Decide this and record it** — do not scatter
E6 across two folders to avoid the question.

**3. Enablement has no home.** *Decided: ADR-0029 — not a component; each E13 use case is filed
where its data lives and carries `epic: E13`.* E13 — guided and expert modes, method scaffolds, the automation
coach, making the human contribution visible — is real product substance, promised in principle
14, and fits no bounded context because it is about how a person experiences the system.

Same treatment: decide where it lives and record why.

**4. Several use cases are already superseded by ADRs.** At minimum UC-8.5 (cost control) has
been overtaken by ADR-0005's amendments and ADR-0010, and UC-4.5 (self-healing) does not know
about the failure/defect distinction of ADR-0021.

For each: keep the requirement, mark what is superseded, and point at the ADR. **Do not delete
a superseded requirement** — the record of what was once wanted is part of the reasoning.

Version 2 already absorbed some of this: its UC-8.10 speaks of admission control, step
boundaries and "at most one step lost", as ADR-0005 does, and its UC-4.5 of a closed loop. It
does not know the failure/defect distinction (ADR-0021), the currency degradation of a limit
(ADR-0005, DEC-0012), or the Takt (ADR-0010).

---

## Version 2 against the version of 2026-09-01

What version 2 changed that matters for the repository. Everything else is wording.

- **Vision (ch. 1).** The target is named: the *virtual agent business*, every department run as
  orchestrated process chains, people as owners and deciders. And: what Taktus produces —
  assistants, dashboards, documentation, skills — is always a Taktus process or artifact in an
  open format, never compulsory. `vision/vision.md` carries both.
- **Market (ch. 2).** Dated September 2026. Two categories added, personal agent runtimes (a
  worker candidate, not a competitor) and observability platforms (an optional backend); a ninth
  gap, "own core, interchangeable execution".
- **Principles (ch. 4).** Principle 1 adds that what Taktus produces is an open artifact, never an
  obligation; principle 10 names the levels by the loop terminology — human-in-, on-, out-of-the-
  loop — and its top as the virtual agent business; principle 13 adds execution units and makes
  itself checkable by the removal test. `vision/principles.md` says all three.
- **Architecture guardrails (ch. 5), new.** Three layers, the three adapter types, the removal
  test, capabilities instead of product names, telemetry from day one, the integration code in
  two tiers with maturity levels, command and rollout channels. Almost all of it is in the ADRs;
  the skill format and the channel distinction are not (the chapter table above).
- **Actors (ch. 6).** Workers — "they execute, they do not decide".
- **Use cases (ch. 7).** New: UC-1.7, UC-5.8, UC-6.7, UC-8.11, epics E14 and E15, and the rule that
  E1, E4, E5 (at least 5.4), E6 (at least 6.1 and the personal view of 6.4), E7, E8 (8.1 to 8.5),
  E10, E11 (11.1, 11.4) and E14 are mandatory for every target group, while E2, E3, E9, 11.3, E12
  and E15 are optional for individuals and families. Changed requirements: UC-1.1 (every command
  carries identity, context and reply address; channels connected in the order people already
  work), UC-4.4 and UC-4.5 (recurring corrections become draft skills; the closed loop, no open
  loops), UC-5.4 (one of three adapter types, with a maturity level), UC-6.1 (which worker; fed
  from the worker event stream; exportable as a telemetry signal), UC-6.3 (the skills a process
  uses; the removal test as its counterpart), UC-7.1 (the loop-named levels; level 4 is the
  virtual agent business, with the emergency stop, reporting and escalation still in force),
  UC-7.3 (least privilege down to the worker), UC-8.1 (the model contract named), UC-8.3 (local
  inference as the default path), UC-8.4 (skill changes are evaluated too), UC-8.9 (workers and
  connectors swapped like models; skills exported; every process exportable as one package;
  the removal test), UC-8.10 (admission control, step boundaries), UC-10.2 (identity mapping,
  worker administration, maturity), UC-11.3 (conformity evidence generated from the real
  configuration), UC-11.4 (credentials injected into workers, never stored), UC-12.1 (a rollout
  channel), UC-13.2 and UC-13.3 (scaffolds are skills; the coach feeds the skill lifecycle).
- **Non-goals (ch. 8).** Added: no ERP, accounting system or CRM; no own coding agent or agent
  runtime; no foreign gateway as the core; nothing Taktus produces is compulsory. The model-training
  non-goal is unchanged in version 2 and corrected in `vision/non-goals.md` by ADR-0004.
- **Development path (ch. 9), new.** Five phases, superseded by the roadmap; its ordering rule is
  the roadmap's; "Taktus builds Taktus — every friction is a product finding".
- **Beyond v1 (ch. 10), new.** Seven ideas; already taken into v1: generated conformity evidence,
  the bus-factor index, local inference as default, a process exported as one package.
- **Open questions (ch. 11), new.** Nine; question 7 is now precise — automatic skill approval at
  level 4 after n evals is required, the question is a floor for n (DEC-0028); question 9 names
  tax advice and labour law as the reviewers' expertise (DEC-0029).

---

## Requirements the owner stated outside the definition

Stated by the owner in conversation. They are requirements, not ideas, and are written as use
cases in the step and the component named — not before, so that no two sessions write in
`docs/usecases/` at once.

**The owner-facing channel** — `reporting/`, step 4. One event, three renderings, all from the
ledger: a repository text — English, minimal, durable, only what the code needs; a message in the
owner's chosen channel — German, with the context needed to act and links to the files, issues
and pull requests; and a view in the web app with its history. The owner answers in the channel,
and Taktus files the result where it belongs — a decision record, a pull-request comment, code. A
report names what is needed, the steps to provide it, which work is standing still, and by when.
Where an organisation runs a ticket system, the same report goes there as a task: the channel is
configuration, not architecture. For the Taktus project itself the channels are Slack and the
web app — this tenant's configuration, not a product name in the core — and the owner can ask questions in either and is answered there. It extends
UC-6.2 and ADR-0028, and it is where an answer given in chat becomes a record (ADR-0008:
interpreted, reflected back, confirmed).

**Readable documentation beyond the repository** — epic E13, filed in `knowledge/`, step 4 (ADR-0029
files E13 where its data lives; the source is the knowledge the repository holds).
Administration guides and end-user guides, structured however the organisation keeps them — a
wiki or otherwise. Generated from the repository and kept consistent with it; never a second
source of truth. It is the same obligation as definition UC-1.4, documentation in the
organisation's own knowledge system, applied to Taktus's own documentation.

**The finding** — `reporting/`, step 4. When a project instance meets something the product
lacks — a missing capability, an awkward flow, a connector that can do too little — that is a
product finding, not a support request. It becomes an issue in the Taktus repository with a
reference to the run that surfaced it. First written by hand; later raised by the instance
itself, carrying the run, the block and the waiting time (ADR-0015's blocked-time account). It is
the requirement behind version 2's "every friction is a product finding".

---

## Order of work

The whole migration does not fit in one reviewable pull request. Four, in this order:

1. **`vision/` plus the gates and the use case format.** The foundation everything else is
   checked against.
2. **The use cases of `process`, `run` and `governance`.** The largest group and the one closest
   to what is built, so contradictions surface early. Includes UC-15.3, UC-15.4 and UC-15.5 from
   E15.
3. **`command`, `identity`, `catalog`, `accounting`.** Includes E14 entire, UC-15.1, UC-5.8,
   UC-8.11 and UC-1.7.
4. **`knowledge`, `value`, `ledger`, `reporting`, plus what moves into `blueprints/`.** Includes
   UC-6.7, UC-15.2 and the domain table of UC-15.1, and the three requirements the owner stated
   outside the definition. Findings 2 and 3 were decided in step 1, so that the use cases of this
   step have a folder to go to.

Delete this file with the fourth.
