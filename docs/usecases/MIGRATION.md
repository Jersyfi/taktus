# Migrating the project definition

The project definition lived outside the repository. This file says where each part goes, what
is superseded, and what has to be decided during the move.

**It is a working document.** When the migration is complete it is deleted, and nothing here
survives except in the files it points to.

**Where it stands (2026-09-29):** step 1 is done — `docs/vision/`, the use case format, the gates
`make gate-vision` and `make gate-usecases`, the two rules in `CLAUDE.md` and in the anchor files,
findings 1 to 3 decided, and thirteen use cases seeded so that every principle is served (their
requirements are DEC-0030). Steps 2 to 4 are open. `docs/status.md` §1 says the same.

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
| 2 Market analysis | → `vision/market.md`. **Marked stale.** Unsourced figures, not maintained |
| 3 Naming | → `vision/history.md`. Settled |
| 4 Guiding principles | → `vision/principles.md`. **Each now carries its reasoning and what it forbids.** 2, 8 and 13 substantially reworked |
| 5 Architecture guardrails | Dissolved into the ADRs. Reasoning kept in `vision/history.md` |
| 6 Actors | → `vision/personas.md` |
| 7 Use cases | → `usecases/`, by component. See below |
| 8 Non-goals | → `vision/non-goals.md`. **One corrected**: model training |
| 9 Development path | Superseded by `docs/roadmap.md` |
| 10 Beyond v1 | → `vision/beyond-1.0.md` |
| 11 Open questions | → `vision/history.md`; the two still open become decision requests |

---

## The use cases, by epic

Components as under `src/taktus/components/`. Where an epic describes a *deployment* rather than
a capability of the core, it belongs in `blueprints/`, not here.

| Epic | Goes to | Notes |
|---|---|---|
| **E1** Command, co-planning, interaction | `command/`, and UC-1.4 and UC-1.6 to `identity/` | UC-1.8 (session with project knowledge) was added later and must be included |
| **E2** Engineering orchestration | **`blueprints/dev-orchestration/`** | Not core use cases. They describe one deployment of the core, and two of them already run |
| **E3** Repository hygiene | **`blueprints/dev-orchestration/`** | Same |
| **E4** Process engine | `process/` and `run/` | The largest group, and the one with the numbering problem below |
| **E5** Integration and knowledge | `knowledge/`; UC-5.1, 5.2, 5.4 are architecture and already decided | UC-5.8 (observability platforms) is optional and stays optional |
| **E6** Reporting and transparency | a new component, **`reporting`** (ADR-0029); UC-6.1 to `ledger/`, UC-6.3 to `process/` | UC-6.3 is the takeover test; UC-6.7 the bus-factor index. Finding 2, decided |
| **E7** Governance and autonomy | `governance/` | UC-7.4 (decision request) was added later and is largely built |
| **E8** Model platform | `catalog/` and `accounting/` | UC-8.5 must be reconciled with ADR-0005 and ADR-0010, which have moved well beyond it |
| **E9** Controlling | `value/` | UC-9.5 (bottleneck and waiting analysis) was added later |
| **E10** Platform and administration | Mostly architecture, already decided. **UC-10.3 (usability for non-technical people)** goes to `command/` (ADR-0029) | |
| **E11** Security, privacy, European values | `governance/` | Needs a check against what exists: much is claimed, little is built |
| **E12** Assistant factory | `catalog/` and `blueprints/` | Depends on E8; not before the catalogue exists |
| **E13** Enablement | no component of its own (ADR-0029): `command/`, `catalog/`, `reporting/`, each with `epic: E13` | Finding 3, decided |
| **E14** Execution layer: workers and skills | `catalog/` for skills; the worker contract is decided and built | |
| **E15** Virtual agent business | **`blueprints/`** | Domain blueprints, not core use cases. UC-15.5 (responsibility anchor) is an exception and belongs in `governance/` |

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

---

## Order of work

The whole migration does not fit in one reviewable pull request. Four, in this order:

1. **`vision/` plus the gates and the use case format.** The foundation everything else is
   checked against.
2. **The use cases of `process`, `run` and `governance`.** The largest group and the one closest
   to what is built, so contradictions surface early.
3. **`command`, `identity`, `catalog`, `accounting`.**
4. **`knowledge`, `value`, `ledger`, `reporting`, plus what moves into `blueprints/`.** Findings 2
   and 3 were decided in step 1, so that the use cases of this step have a folder to go to.

Delete this file with the fourth.
